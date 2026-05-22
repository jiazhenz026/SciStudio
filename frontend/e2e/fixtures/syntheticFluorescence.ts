import fs from "node:fs/promises";
import path from "node:path";
import { deflateSync } from "node:zlib";

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function crc32(buffer: Buffer): number {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) {
      crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type: string, data: Buffer): Buffer {
  const typeBuffer = Buffer.from(type, "ascii");
  const length = Buffer.alloc(4);
  const crc = Buffer.alloc(4);
  length.writeUInt32BE(data.length, 0);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuffer, data])), 0);
  return Buffer.concat([length, typeBuffer, data, crc]);
}

function fluorescenceValue(x: number, y: number, width: number, height: number): number {
  const spots = [
    { x: 0.34, y: 0.38, r: 0.11, amp: 220 },
    { x: 0.63, y: 0.58, r: 0.16, amp: 180 },
    { x: 0.73, y: 0.25, r: 0.08, amp: 130 },
  ];
  const nx = x / (width - 1);
  const ny = y / (height - 1);
  const background = 14 + ((x * 13 + y * 17) % 11);
  const signal = spots.reduce((sum, spot) => {
    const dx = nx - spot.x;
    const dy = ny - spot.y;
    const falloff = Math.exp(-(dx * dx + dy * dy) / (2 * spot.r * spot.r));
    return sum + spot.amp * falloff;
  }, background);
  return Math.max(0, Math.min(255, Math.round(signal)));
}

export async function createSyntheticFluorescencePng(filePath: string, width = 64, height = 64): Promise<void> {
  const rawRows: Buffer[] = [];
  for (let y = 0; y < height; y += 1) {
    const row = Buffer.alloc(1 + width);
    row[0] = 0;
    for (let x = 0; x < width; x += 1) {
      row[1 + x] = fluorescenceValue(x, y, width, height);
    }
    rawRows.push(row);
  }

  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 0;
  header[10] = 0;
  header[11] = 0;
  header[12] = 0;

  const png = Buffer.concat([
    PNG_SIGNATURE,
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(Buffer.concat(rawRows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, png);
}

export async function createSyntheticFluorescenceTiff(filePath: string, width = 64, height = 64): Promise<void> {
  const pixels = Buffer.alloc(width * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      pixels[y * width + x] = fluorescenceValue(x, y, width, height);
    }
  }

  const entries = [
    { tag: 256, type: 4, count: 1, value: width },
    { tag: 257, type: 4, count: 1, value: height },
    { tag: 258, type: 3, count: 1, value: 8 },
    { tag: 259, type: 3, count: 1, value: 1 },
    { tag: 262, type: 3, count: 1, value: 1 },
    { tag: 273, type: 4, count: 1, value: 0 },
    { tag: 277, type: 3, count: 1, value: 1 },
    { tag: 278, type: 4, count: 1, value: height },
    { tag: 279, type: 4, count: 1, value: pixels.length },
    { tag: 284, type: 3, count: 1, value: 1 },
  ].sort((left, right) => left.tag - right.tag);

  const ifdLength = 2 + entries.length * 12 + 4;
  const pixelOffset = 8 + ifdLength;
  const tiff = Buffer.alloc(pixelOffset + pixels.length);
  tiff.write("II", 0, "ascii");
  tiff.writeUInt16LE(42, 2);
  tiff.writeUInt32LE(8, 4);
  tiff.writeUInt16LE(entries.length, 8);

  entries.forEach((entry, index) => {
    const offset = 10 + index * 12;
    const value = entry.tag === 273 ? pixelOffset : entry.value;
    tiff.writeUInt16LE(entry.tag, offset);
    tiff.writeUInt16LE(entry.type, offset + 2);
    tiff.writeUInt32LE(entry.count, offset + 4);
    if (entry.type === 3 && entry.count === 1) {
      tiff.writeUInt16LE(value, offset + 8);
      tiff.writeUInt16LE(0, offset + 10);
    } else {
      tiff.writeUInt32LE(value, offset + 8);
    }
  });
  tiff.writeUInt32LE(0, 10 + entries.length * 12);
  pixels.copy(tiff, pixelOffset);

  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, tiff);
}
