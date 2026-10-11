// 저장소 루트의 웹앱(index.html, icons)을 데스크톱 앱 안으로 복사합니다.
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const out = path.join(__dirname, "app");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(path.join(out, "icons"), { recursive: true });

fs.copyFileSync(path.join(root, "index.html"), path.join(out, "index.html"));
for (const f of fs.readdirSync(path.join(root, "icons"))) {
  fs.copyFileSync(path.join(root, "icons", f), path.join(out, "icons", f));
}

// 앱 아이콘 (electron-builder가 윈도우 .ico, 맥 .icns로 변환)
fs.mkdirSync(path.join(__dirname, "build"), { recursive: true });
fs.copyFileSync(path.join(root, "icons", "icon-512.png"), path.join(__dirname, "build", "icon.png"));
console.log("web app copied to", out);
