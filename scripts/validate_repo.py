#!/usr/bin/env python3
"""저장소 구조와 민감 정보 검사.

사용: python3 scripts/validate_repo.py [--root DIR] [--terms FILE]
  --terms: 한 줄에 하나씩 금지어(대소문자 무시)를 적은 로컬 파일. 저장소에 커밋하지 않는다.
종료 코드: 0 통과, 1 실패.
"""
import argparse
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_SKILL_LINES = 500
MAX_DESC = 1024
TEXT_EXT = {".md", ".json", ".py", ".js", ".yml", ".yaml", ".txt", ".toml", ""}
SKIP_NAMES = {"LICENSE"}
SKIP_DIRS = {".git", "node_modules", "__pycache__"}

# 문서용 예약 주소와 로컬 주소는 허용한다.
SAFE_IP = re.compile(r"^(127\.|0\.0\.0\.0|192\.0\.2\.|198\.51\.100\.|203\.0\.113\.)")
SENSITIVE = [
    ("notion-id", re.compile(r"\b[0-9a-f]{32}\b")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("ipv4", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    ("home-path", re.compile(r"(?:/home/[a-z][\w.-]*/|C:\\Users\\)")),
    ("real-advisory-id", re.compile(r"\b(?:CVE-(?!2099-)\d{4}-\d{4,}|RHSA-(?!2099:)\d{4}:\d+)")),
    ("token", re.compile(r"\b(?:ghp_|github_pat_|AKIA)[A-Za-z0-9_]{12,}|\bsk-[A-Za-z0-9]{20,}")),
]
SAFE_EMAIL = re.compile(r"@(example\.(com|org)|users\.noreply\.github\.com)$|^noreply@")


def read_json(path, errors):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        errors.append(f"{path}: JSON을 읽을 수 없음 ({e})")
        return None


def frontmatter(text):
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text.lstrip("\ufeff"), re.S)
    if not m:
        return None
    out = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep:
            out[k.strip()] = v.strip().strip('"')
            out["_raw_" + k.strip()] = v.strip()
    return out


def iter_text_files(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            p = Path(dp) / fn
            if fn in SKIP_NAMES or p.suffix not in TEXT_EXT:
                continue
            yield p


def check_manifests(root, errors):
    mp = root / ".claude-plugin" / "marketplace.json"
    if not mp.is_file():
        errors.append("marketplace.json 없음: .claude-plugin/marketplace.json")
        return []
    mk = read_json(mp, errors)
    if not isinstance(mk, dict):
        return []
    for key in ("name", "owner", "plugins"):
        if key not in mk:
            errors.append(f"marketplace.json: '{key}' 없음")
    if not (isinstance(mk.get("owner"), dict) and mk["owner"].get("name")):
        errors.append("marketplace.json: owner.name 없음")
    version_file = root / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else None
    if version is None:
        errors.append("VERSION 파일 없음")
    plugin_dirs = []
    plugins = mk.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        errors.append("marketplace.json: plugins가 비어 있음")
        return []
    for entry in plugins:
        name, src = entry.get("name"), entry.get("source", "")
        if not name or not str(src).startswith("./"):
            errors.append(f"marketplace.json: 플러그인 항목 형식 오류 {entry}")
            continue
        if ".." in str(src):
            errors.append(f"marketplace.json: source에 '..' 사용 불가 {src}")
            continue
        pdir = root / src[2:]
        pj = pdir / ".claude-plugin" / "plugin.json"
        if not pj.is_file():
            errors.append(f"{src}: .claude-plugin/plugin.json 없음")
            continue
        meta = read_json(pj, errors) or {}
        if meta.get("name") != name:
            errors.append(f"{pj}: name '{meta.get('name')}' != marketplace '{name}'")
        for label, val in (("marketplace", entry.get("version")), ("plugin.json", meta.get("version"))):
            if version and val != version:
                errors.append(f"버전 불일치: {label}={val}, VERSION={version}")
        cx = pdir / ".codex-plugin" / "plugin.json"
        if not cx.is_file():
            errors.append(f"{src}: .codex-plugin/plugin.json 없음")
        else:
            cm = read_json(cx, errors) or {}
            if cm.get("name") != name:
                errors.append(f"{cx}: name '{cm.get('name')}' != '{name}'")
            if version and cm.get("version") != version:
                errors.append(f"버전 불일치: codex plugin.json={cm.get('version')}, VERSION={version}")
            skills = cm.get("skills")
            if not isinstance(skills, str) or not skills.strip().lstrip("./") or not (pdir / skills.lstrip("./")).is_dir():
                errors.append(f"{cx}: skills 경로 없음")
        # Codex canonical 포터블 매니페스트. 없거나 버전이 어긋나면 설치본이 갱신되지 않는다.
        rp = pdir / "plugin.json"
        if not rp.is_file():
            errors.append(f"{src}: plugin.json 없음 (Codex canonical)")
        else:
            rm = read_json(rp, errors) or {}
            if rm.get("name") != name:
                errors.append(f"{rp}: name '{rm.get('name')}' != '{name}'")
            if version and rm.get("version") != version:
                errors.append(f"버전 불일치: plugin.json={rm.get('version')}, VERSION={version}")
        plugin_dirs.append(pdir)
    check_codex_marketplace(root, [e.get("name") for e in plugins], errors)
    check_grok_marketplace(root, [e.get("name") for e in plugins], version, errors)
    metadata_version = (mk.get("metadata") or {}).get("version")
    if version and metadata_version and metadata_version != version:
        errors.append(f"버전 불일치: marketplace metadata={metadata_version}, VERSION={version}")
    return plugin_dirs


def check_codex_marketplace(root, names, errors):
    mp = root / ".agents" / "plugins" / "marketplace.json"
    if not mp.is_file():
        errors.append("Codex 마켓플레이스 없음: .agents/plugins/marketplace.json")
        return
    mk = read_json(mp, errors)
    if not isinstance(mk, dict):
        return
    entries = {e.get("name"): e for e in mk.get("plugins", [])}
    for n in names:
        e = entries.get(n)
        if not e:
            errors.append(f"Codex 마켓플레이스에 '{n}' 없음")
            continue
        src = e.get("source")
        path = src.get("path") if isinstance(src, dict) else src
        if ".." in str(path):
            errors.append(f"Codex 마켓플레이스: '{n}' source에 '..' 사용 불가 {path}")
        elif not str(path).startswith("./") or not (root / str(path)[2:]).is_dir():
            errors.append(f"Codex 마켓플레이스: '{n}' source 경로 오류 {path}")
        pol = e.get("policy") or {}
        if not (pol.get("installation") and pol.get("authentication") and e.get("category")):
            errors.append(f"Codex 마켓플레이스: '{n}' policy/category 누락")


def check_grok_marketplace(root, names, version, errors):
    mp = root / ".grok-plugin" / "marketplace.json"
    if not mp.is_file():
        errors.append("Grok 마켓플레이스 없음: .grok-plugin/marketplace.json")
        return
    mk = read_json(mp, errors)
    if not isinstance(mk, dict):
        return
    for key in ("name", "description", "owner", "plugins"):
        if key not in mk:
            errors.append(f"Grok 마켓플레이스: '{key}' 없음")
    entries = {e.get("name"): e for e in mk.get("plugins", [])}
    for n in names:
        e = entries.get(n)
        if not e:
            errors.append(f"Grok 마켓플레이스에 '{n}' 없음")
            continue
        src = e.get("source") or {}
        path = src.get("path", "")
        if ".." in str(path):
            errors.append(f"Grok 마켓플레이스: '{n}' source에 '..' 사용 불가 {path}")
        elif src.get("type") != "local" or not str(path).startswith("./") or not (root / str(path)[2:]).is_dir():
            errors.append(f"Grok 마켓플레이스: '{n}' source 오류 {src}")
        if version and e.get("version") != version:
            errors.append(f"버전 불일치: grok marketplace={e.get('version')}, VERSION={version}")


def check_skills(plugin_dirs, errors):
    for pdir in plugin_dirs:
        sdir = pdir / "skills"
        if not sdir.is_dir():
            errors.append(f"{pdir}: skills 디렉터리 없음")
            continue
        for skill in sorted(p for p in sdir.iterdir() if p.is_dir()):
            md = skill / "SKILL.md"
            if not md.is_file():
                errors.append(f"{skill}: SKILL.md 없음")
                continue
            text = md.read_text(encoding="utf-8")
            fm = frontmatter(text)
            if fm is None:
                errors.append(f"{md}: frontmatter 없음")
                continue
            if fm.get("name") != skill.name:
                errors.append(f"{md}: name '{fm.get('name')}' != 디렉터리 '{skill.name}'")
            desc = fm.get("description", "")
            # 엄격한 YAML 파서(Codex 등)에서 깨지는 비인용 스칼라를 막는다.
            raw = fm.get("_raw_description", "")
            if raw and not raw.startswith(('"', "'")) and (": " in raw or " #" in raw or raw[0] in "[{&*!|>%@`"):
                errors.append(f"{md}: description에 따옴표 없는 ': ' 또는 ' #' (YAML 오류 위험)")
            if not desc:
                errors.append(f"{md}: description 없음")
            elif len(desc) > MAX_DESC:
                errors.append(f"{md}: description {len(desc)}자 (최대 {MAX_DESC})")
            if text.count("\n") + 1 > MAX_SKILL_LINES:
                errors.append(f"{md}: {MAX_SKILL_LINES}줄 초과")
            for ref in set(re.findall(r"`((?:references|scripts)/[^`\s*]+\.\w+)`", text)):
                if not (skill / ref).exists():
                    errors.append(f"{md}: 참조 파일 없음 {ref}")
            for ref in set(re.findall(r"\]\(((?:references|scripts)/[^)\s#]+)\)", text)):
                if not (skill / ref).exists():
                    errors.append(f"{md}: 링크 대상 없음 {ref}")
            for pat in set(re.findall(r"`(references/[^`\s]*\*[^`\s]*)`", text)):
                if not list(skill.glob(pat)):
                    errors.append(f"{md}: 패턴과 일치하는 파일 없음 {pat}")


def check_code(root, errors):
    node = shutil.which("node")
    for p in root.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix == ".py":
            try:
                with tempfile.TemporaryDirectory() as td:
                    py_compile.compile(str(p), cfile=os.path.join(td, "x.pyc"), doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(f"{p}: Python 문법 오류 {e.msg.strip()}")
        elif p.suffix == ".js" and node:
            r = subprocess.run([node, "--check", str(p)], capture_output=True, text=True)
            if r.returncode:
                errors.append(f"{p}: JS 문법 오류 {r.stderr.strip().splitlines()[-1] if r.stderr else ''}")


def check_sensitive(root, extra_terms, errors):
    terms = [t.lower() for t in extra_terms if t.strip()]
    for p in iter_text_files(root):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = p.relative_to(root)
        low = text.lower()
        for t in terms:
            if t in low:
                errors.append(f"{rel}: 금지어 포함")
        for kind, rx in SENSITIVE:
            # 실제 CVE/RHSA 값이 허용되는 자리: 평가 케이스 입력과 rhel-cve 스킬의 실사례·검사기 픽스처.
            if kind == "real-advisory-id" and ("eval_cases" in rel.parts or "rhel-cve" in rel.parts):
                continue
            for m in rx.finditer(text):
                val = m.group(0)
                if kind == "ipv4" and (SAFE_IP.match(val) or any(int(x) > 255 for x in val.split("."))):
                    continue
                if kind == "email" and SAFE_EMAIL.search(val):
                    continue
                errors.append(f"{rel}: 민감 패턴({kind}) 의심")
                break


def validate(root, extra_terms=()):
    root = Path(root)
    errors = []
    plugin_dirs = check_manifests(root, errors)
    check_skills(plugin_dirs, errors)
    check_code(root, errors)
    check_sensitive(root, extra_terms, errors)
    return errors


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--terms", help="금지어 목록 파일(로컬 전용)")
    args = ap.parse_args(argv)
    terms = []
    path = args.terms or os.environ.get("MYWAY_BANNED_TERMS_FILE")
    if path:
        terms = Path(path).read_text(encoding="utf-8").splitlines()
    errors = validate(args.root, terms)
    if errors:
        print(f"FAIL {len(errors)}건")
        for e in errors:
            print(" -", e)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
