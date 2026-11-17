const fs = require("fs");
const path = require("path");

function outputPath(outDir, name) {
  if (typeof name !== "string" || !name || name === "." || name === ".." ||
      /[\\/:\x00-\x1f]/.test(name) || path.basename(name) !== name || /[. ]$/.test(name) ||
      /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) {
    throw new Error("output must be a filename inside OUT_DIR");
  }
  return path.join(outDir, name);
}

function copyExclusive(source, target) {
  fs.copyFileSync(source, target, fs.constants.COPYFILE_EXCL);
}

module.exports = { outputPath, copyExclusive };
