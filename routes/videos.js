const fs = require('fs');
const path = require('path');
// In your backend video routes file (e.g., routes/videos.js or server.js)
const express = require('express');
const router = express.Router();

// New route for streaming videos.
// If your video routes are mounted at '/api/videos', this will be accessible at:
// GET /api/videos/stream/:filename
router.get('api/videos/stream/:filename', (req, res) => {
  const { filename } = req.params;
  // This assumes your 'uploads' directory is in the root of your backend project.
  // Adjust the path if your project structure is different.
  const videoPath = path.join(__dirname, '..', 'uploads', filename);

  // Check if the file exists
  if (!fs.existsSync(videoPath)) {
    return res.status(404).send('Video not found.');
  }

  const stat = fs.statSync(videoPath);
  const fileSize = stat.size;
  const range = req.headers.range;

  if (range) {
    // Handle range requests (for seeking)
    const parts = range.replace(/bytes=/, "").split("-");
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
    
    if (start >= fileSize) {
      res.status(416).send('Requested range not satisfiable\\n' + start + ' >= ' + fileSize);
      return;
    }

    const chunksize = (end - start) + 1;
    const file = fs.createReadStream(videoPath, { start, end });
    const head = {
      'Content-Range': `bytes ${start}-${end}/${fileSize}`,
      'Accept-Ranges': 'bytes',
      'Content-Length': chunksize,
      'Content-Type': 'video/mp4',
    };

    res.writeHead(206, head); // 206 Partial Content
    file.pipe(res);
  } else {
    // Handle requests without a range header (play from the beginning)
    const head = {
      'Content-Length': fileSize,
      'Content-Type': 'video/mp4',
    };
    res.writeHead(200, head); // 200 OK
    fs.createReadStream(videoPath).pipe(res);
  }
});

