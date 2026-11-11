const { app, BrowserWindow } = require('electron');
const fs = require('fs');
const path = require('path');

app.disableHardwareAcceleration();

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    show: false,
    webPreferences: {
      offscreen: true
    }
  });

  const htmlPath = process.argv[2];
  const pdfPath = process.argv[3];

  await win.loadURL('file:///' + path.resolve(htmlPath).replace(/\\/g, '/'));
  
  const pdfData = await win.webContents.printToPDF({
    pageSize: 'A4',
    printBackground: true,
    margins: {
      top: 0,
      bottom: 0,
      left: 0,
      right: 0
    }
  });

  fs.writeFileSync(pdfPath, pdfData);
  console.log('PDF_SUCCESS:', pdfPath, pdfData.length);
  app.exit(0);
});
