import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, Notification } from 'electron'
import { join } from 'path'
import { is } from '@electron-toolkit/utils'
import { setupIpcHandlers } from './ipc'

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 420,
    height: 680,
    show: false,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    backgroundColor: '#0d0d0d',
    vibrancy: 'under-window',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  })

  mainWindow.on('blur', () => {
    mainWindow?.hide()
  })

  if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

function createTray(): void {
  const icon = nativeImage.createEmpty()
  tray = new Tray(icon)

  tray.setToolTip('Zero-Alpha-Beta')

  tray.on('click', () => {
    if (!mainWindow) return

    if (mainWindow.isVisible()) {
      mainWindow.hide()
    } else {
      const trayBounds = tray!.getBounds()
      const windowBounds = mainWindow.getBounds()

      const x = Math.round(trayBounds.x + trayBounds.width / 2 - windowBounds.width / 2)
      const y = Math.round(trayBounds.y + trayBounds.height + 4)

      mainWindow.setPosition(x, y)
      mainWindow.show()
      mainWindow.focus()
    }
  })

  const contextMenu = Menu.buildFromTemplate([
    { label: 'Zero-Alpha-Beta', enabled: false },
    { type: 'separator' },
    { label: '열기', click: () => mainWindow?.show() },
    { type: 'separator' },
    { label: '종료', click: () => app.quit() },
  ])

  tray.on('right-click', () => {
    tray?.popUpContextMenu(contextMenu)
  })
}

app.whenReady().then(() => {
  app.setName('Zero-Alpha-Beta')

  if (process.platform === 'darwin') {
    app.dock.hide()
  }

  createWindow()
  createTray()
  setupIpcHandlers()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

export { mainWindow }
