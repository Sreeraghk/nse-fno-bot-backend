# NSE F&O OI Tracker - Backend Deployment Guide

## Overview

This is the backend service for the NSE F&O OI Tracker Android application. It provides real-time data on Open Interest changes for NSE F&O stocks and serves this data via a REST API.

## Deployment to Railway

### Prerequisites
- A Railway account (free tier available at https://railway.app)
- Git installed on your computer

### Step-by-Step Deployment

1. **Initialize Git Repository**
   ```bash
   git init
   git add .
   git commit -m "NSE F&O Bot Backend - Initial deployment"
   ```

2. **Create Railway Project**
   - Go to https://railway.app and log in
   - Click "New Project"
   - Select "Deploy from GitHub" or "Deploy from Git Repo"
   - Follow the prompts to connect your repository

3. **Railway will automatically:**
   - Detect the `Dockerfile`
   - Build the Docker image
   - Deploy the FastAPI application
   - Provide a public URL (e.g., `https://nse-fno-bot-xxxx.up.railway.app`)

4. **Get Your API URL**
   - After deployment, go to your Railway project settings
   - Find the "Domains" section
   - Copy the public domain URL
   - This is your **BACKEND_API_URL** (e.g., `https://nse-fno-bot-xxxx.up.railway.app`)

5. **Set Up Cron Job (Optional but Recommended)**
   - In Railway, create a new "Cron" service
   - Set the command to: `python cron_job.py`
   - Set the schedule to: `*/5 * * * *` (every 5 minutes)
   - This ensures data is refreshed every 5 minutes

## API Endpoints

Once deployed, your backend will provide the following endpoints:

### Get Filtered Stocks
```
GET /api/v1/stocks
```
Returns a list of stocks where OI change from last session end is > Variable A, sorted by change percentage.

### Get Stock Details
```
GET /api/v1/stock/{symbol}
```
Returns detailed OI information for a specific stock.

### Get Current Settings
```
GET /api/v1/settings
```
Returns the current Variable A and Variable B values.

### Update Settings
```
POST /api/v1/settings
Content-Type: application/json

{
  "variable_a": 3.0,
  "variable_b": 1.0
}
```

### Get System Status
```
GET /api/v1/status
```
Returns the current status of the backend service.

## Data Processing

The backend:
1. Scrapes real-time NSE F&O data every 5 minutes (via cron job)
2. Calculates OI changes from the last trading session end
3. Tracks live OI changes between data points
4. Stores historical data for the last 3 trading days
5. Serves filtered data based on user-defined criteria

## Important Notes

- The NSE website uses Akamai protection, so scraping can be unstable
- The backend uses proper headers and cookies to mimic browser requests
- If scraping fails, the backend serves dummy data for testing
- All data is stored in-memory (no database required for free tier)
- The backend automatically cleans up old data

## Troubleshooting

**Backend not starting?**
- Check Railway logs for errors
- Ensure all dependencies in `requirements.txt` are installed
- Verify the Dockerfile is correct

**No data showing?**
- The cron job may not be running
- Check if NSE website is accessible
- Try accessing `/api/v1/status` to check backend health

**API returning errors?**
- Ensure the backend URL is correct
- Check that the API endpoint paths match exactly
- Verify network connectivity

## Support

For issues or questions, check the logs in your Railway dashboard.

