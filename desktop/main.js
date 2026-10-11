// 차트 시그널 데스크톱 앱 (Electron)
// 앱 화면은 함께 들어 있는 index.html을 쓰고, 시세·검색·뉴스는 데이터 서버(chart-signal.onrender.com)에서 받습니다.
const { app, BrowserWindow, shell, Menu } = require("electron");
const path = require("path");

if (!app.requestSingleInstanceLock()) {
  app.quit();
}

let win = null;

function isExternal(url) {
  return /^https?:\/\//i.test(url);
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 380,
    minHeight: 600,
    title: "차트 시그널",
    backgroundColor: "#12161a",
    autoHideMenuBar: true,
    icon: path.join(__dirname, "app", "icons", "icon-512.png"),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      spellcheck: false,
    },
  });

  win.loadFile(path.join(__dirname, "app", "index.html"));

  // 뉴스 기사 등 바깥 링크는 기본 브라우저로 엽니다
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isExternal(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (isExternal(url)) {
      e.preventDefault();
      shell.openExternal(url);
    }
  });
  win.on("closed", () => { win = null; });
}

app.on("second-instance", () => {
  if (win) {
    if (win.isMinimized()) win.restore();
    win.focus();
  }
});

app.whenReady().then(() => {
  if (process.platform !== "darwin") Menu.setApplicationMenu(null);
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
