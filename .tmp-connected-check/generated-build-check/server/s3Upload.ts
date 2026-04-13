import { S3Client, PutObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { randomBytes } from "crypto";
import path from "path";

// Validate required environment variables
if (!process.env.AWS_REGION) {
  throw new Error('Missing required AWS secret: AWS_REGION');
}
if (!process.env.S3_BUCKET) {
  throw new Error('Missing required AWS secret: S3_BUCKET');
}
if (!process.env.AWS_ACCESS_KEY_ID) {
  throw new Error('Missing required AWS secret: AWS_ACCESS_KEY_ID');
}
if (!process.env.AWS_SECRET_ACCESS_KEY) {
  throw new Error('Missing required AWS secret: AWS_SECRET_ACCESS_KEY');
}

// Initialize S3 client
const s3Client = new S3Client({
  region: process.env.AWS_REGION,
  credentials: {
    accessKeyId: process.env.AWS_ACCESS_KEY_ID,
    secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  },
});

const BUCKET_NAME = process.env.S3_BUCKET;

/**
 * Generate a unique filename with timestamp and random hash
 */
function generateUniqueFilename(originalFilename: string, prefix: string): string {
  const timestamp = Date.now();
  const randomHash = randomBytes(8).toString('hex');
  const ext = path.extname(originalFilename);
  const sanitizedName = path.basename(originalFilename, ext).replace(/[^a-zA-Z0-9-_]/g, '_');
  
  return `${prefix}/${timestamp}-${randomHash}-${sanitizedName}${ext}`;
}

/**
 * Upload a file to S3 and return the public URL
 */
export async function uploadToS3(
  fileBuffer: Buffer,
  originalFilename: string,
  contentType: string,
  prefix: string = 'uploads'
): Promise<string> {
  const filename = generateUniqueFilename(originalFilename, prefix);

  const command = new PutObjectCommand({
    Bucket: BUCKET_NAME,
    Key: filename,
    Body: fileBuffer,
    ContentType: contentType,
  });

  try {
    await s3Client.send(command);
    
    // Generate the public URL
    const url = `https://${BUCKET_NAME}.s3.${process.env.AWS_REGION}.amazonaws.com/${filename}`;
    return url;
  } catch (error) {
    console.error('S3 upload error:', error);
    throw new Error('Failed to upload file to S3');
  }
}

/**
 * Upload audio file to S3
 */
export async function uploadAudioToS3(
  fileBuffer: Buffer,
  originalFilename: string,
  contentType: string
): Promise<string> {
  return uploadToS3(fileBuffer, originalFilename, contentType, 'audio');
}

/**
 * Upload cover image to S3
 */
export async function uploadCoverToS3(
  fileBuffer: Buffer,
  originalFilename: string,
  contentType: string
): Promise<string> {
  return uploadToS3(fileBuffer, originalFilename, contentType, 'covers');
}

/**
 * Upload playlist cover image to S3
 */
export async function uploadPlaylistCoverToS3(
  fileBuffer: Buffer,
  originalFilename: string,
  contentType: string
): Promise<string> {
  return uploadToS3(fileBuffer, originalFilename, contentType, 'playlist-covers');
}

/**
 * Extract S3 key from a full S3 URL
 */
export function extractS3Key(s3Url: string): string {
  try {
    const url = new URL(s3Url);
    // Remove leading slash from pathname
    return url.pathname.substring(1);
  } catch (error) {
    // If it's already just a key (not a full URL), return as-is
    return s3Url;
  }
}

/**
 * Generate a pre-signed URL for reading an S3 object
 * @param s3UrlOrKey - Either a full S3 URL or just the S3 key
 * @param expiresInSeconds - How long the URL should be valid (default: 1 hour)
 */
export async function generateSignedUrl(
  s3UrlOrKey: string,
  expiresInSeconds: number = 3600
): Promise<string> {
  const key = extractS3Key(s3UrlOrKey);

  const command = new GetObjectCommand({
    Bucket: BUCKET_NAME,
    Key: key,
  });

  try {
    const signedUrl = await getSignedUrl(s3Client, command, { 
      expiresIn: expiresInSeconds 
    });
    return signedUrl;
  } catch (error) {
    console.error('Failed to generate signed URL:', error);
    throw new Error('Failed to generate signed URL');
  }
}
