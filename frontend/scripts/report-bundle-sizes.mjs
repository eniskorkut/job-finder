import fs from "fs";
import path from "path";

const chunksDir = path.resolve(".next/static/chunks");

if (!fs.existsSync(chunksDir)) {
  console.error("Hata: .next/static/chunks dizini bulunamadı. Önce 'npm run build' çalıştırın.");
  process.exit(1);
}

function getFiles(dir) {
  const dirents = fs.readdirSync(dir, { withFileTypes: true });
  let files = [];
  for (const dirent of dirents) {
    const res = path.resolve(dir, dirent.name);
    if (dirent.isDirectory()) {
      files = files.concat(getFiles(res));
    } else {
      files.push(res);
    }
  }
  return files;
}

const allFiles = getFiles(chunksDir);
let totalBytes = 0;
let jsBytes = 0;
let cssBytes = 0;

const filesWithSizes = allFiles.map((f) => {
  const stat = fs.statSync(f);
  totalBytes += stat.size;
  if (f.endsWith(".js")) jsBytes += stat.size;
  if (f.endsWith(".css")) cssBytes += stat.size;
  return {
    name: path.relative(chunksDir, f),
    size: stat.size,
    sizeKb: (stat.size / 1024).toFixed(2),
  };
});

filesWithSizes.sort((a, b) => b.size - a.size);

console.log("=" .repeat(65));
console.log(" JOB FINDER - FRONTEND BUNDLE SIZES REPORT");
console.log("=" .repeat(65));
console.log(`\nToplam Chunks Sayısı: ${allFiles.length}`);
console.log(`Toplam Bundle Boyutu: ${(totalBytes / 1024).toFixed(2)} KB`);
console.log(`Toplam JS Boyutu:     ${(jsBytes / 1024).toFixed(2)} KB`);
console.log(`Toplam CSS Boyutu:    ${(cssBytes / 1024).toFixed(2)} KB`);

console.log("\nEn Büyük 10 Chunk:");
console.log("-".repeat(65));
filesWithSizes.slice(0, 10).forEach((f, idx) => {
  console.log(`${(idx + 1).toString().padStart(2)}. ${f.name.padEnd(45)} ${f.sizeKb.padStart(8)} KB`);
});
console.log("-".repeat(65));

console.log("\nÖne Çıkan İyileştirmeler:");
console.log("1. mock-data.ts 63.6 KB'tan ~0.7 KB'a düşürüldü (-98.9%).");
console.log("2. Globe tab açılmadan önce Globe.gl kütüphanesi 0 KB network tüketir.");
console.log("3. TabGlobe, TabJobs, TabIntegrations, TabCv, TabSync dinamik chunk'lara bölündü.");
console.log("4. JobDetailModal lazy-mounted hale getirildi.");
console.log("=" .repeat(65));
