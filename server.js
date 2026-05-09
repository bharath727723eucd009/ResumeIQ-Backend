const express = require('express');
const cors = require('cors');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5000;

app.use(cors());
app.use(express.json());

app.get('/api/health', (req, res) => {
  res.json({ status: 'OK', message: 'Backend server running' });
});

// Proxy to FastAPI for resume analysis
app.post('/api/analyze-resume', (req, res) => {
  res.json({
    message: 'Use FastAPI backend on port 8000 for resume analysis',
    endpoint: 'http://localhost:8000/api/analyze-resume'
  });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
