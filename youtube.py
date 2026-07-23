import requests
import sys
import logging
import os
import re
from typing import Tuple
import yt_dlp

logger = logging.getLogger(__name__)

# API Configuration
API_TOKEN = getattr(sys.modules.get('config'), 'YT_DLP_API_KEY', os.getenv('YT_DLP_API_KEY', ''))
BASE_URL = getattr(sys.modules.get('config'), 'YT_DLP_BASE_URL', os.getenv('YT_DLP_BASE_URL', 'http://api.nubcoders.com'))

def get_video_info(url_or_query: str, max_results: int = 1) -> Tuple[str, str, int, str, str, int, str, str, str]:
    """Get video info - returns (title, video_id, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken)"""
    logger.info(f"Getting video info for: {url_or_query[:50]}{'...' if len(url_or_query) > 50 else ''}")
    try:
        logger.debug(f"Making API request to {BASE_URL}/info with max_results={max_results}")
        response = requests.get(
            f'{BASE_URL}/info',
            params={'token': API_TOKEN, 'q': url_or_query, 'max_results': max_results},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        logger.debug(f"API response status: {response.status_code}")

        if 'error' in data:
            logger.error(f"API returned error: {data.get('error')}")
            return None, None, None, None, None, None, None, None, data.get('error')
        
        logger.info(f"Successfully retrieved video info: {data.get('title', 'N/A')}")
        return (
            data.get('title', 'N/A'),
            data.get('video_id', 'N/A'),
            data.get('duration', 0),
            data.get('youtube_link', 'N/A'),
            data.get('channel_name', 'N/A'),
            data.get('views', 0),
            data.get('stream_url', 'N/A'),
            data.get('thumbnail', 'N/A'),
            data.get('time_taken', 'N/A')
        )
    except requests.RequestException as e:
        logger.error(f"Request failed for video info: {str(e)}")
        return None, None, None, None, None, None, None, None, str(e)

def format_duration(seconds):
    """Formats duration from seconds to HH:MM:SS or MM:SS"""
    if not isinstance(seconds, (int, float)) or seconds < 0:
        logger.debug(f"format_duration received invalid input: {seconds} (type: {type(seconds)})")
        return "N/A"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        formatted = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        formatted = f"{minutes:02d}:{secs:02d}"
    
    logger.debug(f"Formatted duration {seconds}s to {formatted}")
    return formatted

def time_to_seconds(time_str):
    stringt = str(time_str)
    logger.debug(f"Converting time {stringt} to seconds")
    try:
        seconds = sum(int(x) * 60**i for i, x in enumerate(reversed(stringt.split(":"))))
        logger.debug(f"Converted {stringt} to {seconds} seconds")
        return seconds
    except Exception as e:
        logger.error(f"Error converting time {stringt} to seconds: {str(e)}")
        return 0

async def handle_youtube_ytdlp(argument):
    """
    Helper function to get YouTube video info using yt-dlp.

    Returns:
        tuple: (title, duration, youtube_link, thumbnail, channel_name, views, video_id)
    """
    try:
        is_url = re.match(r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+", argument)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True, # Get basic info without downloading
            'skip_download': True,
            "cookiesfrombrowser": ("firefox",), # Optional: Use cookies from browser
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            if is_url:
                info_dict = ydl.extract_info(argument, download=False)
            else:
                info_dict = ydl.extract_info(f"ytsearch:{argument}", download=False)['entries'][0]

            if not info_dict:
                return None

            title = info_dict.get('title', 'N/A')
            video_id = info_dict.get('id', 'N/A')
            channel_name = info_dict.get('uploader', 'N/A')
            views = info_dict.get('view_count', 'N/A')
            youtube_link = f"https://www.youtube.com/watch?v={video_id}"

            # Duration can be in seconds or a string, convert to seconds if needed
            duration_raw = info_dict.get('duration', 0)
            if isinstance(duration_raw, str):
                try:
                    duration_sec = time_to_seconds(duration_raw)
                except Exception:
                    duration_sec = 0
            else:
                duration_sec = int(duration_raw) if duration_raw else 0
            
            duration_formatted = format_duration(duration_sec)

            thumbnail_url = 'N/A'
            if 'thumbnails' in info_dict and info_dict['thumbnails']:
                thumbnail_url = info_dict['thumbnails'][-1]['url']

            return (title, duration_formatted, youtube_link, thumbnail_url, channel_name, views, video_id)

    except Exception as e:
        logger.error(f"Error in handle_youtube_ytdlp: {e}")
        return None

async def handle_youtube(argument):
    """
    Main function to get YouTube video information.
    Prioritizes API calls, falls back to yt-dlp.

    Returns:
        tuple: (title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url)
    """
    
    # First try API if token is available
    if API_TOKEN:
        try:
            logger.info("Attempting API request for video info...")
            api_result = get_video_info(argument)

            if api_result and api_result[0] and api_result[0] != "N/A":
                title, video_id, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken = api_result

                # Format duration if it's in seconds
                if isinstance(duration, int):
                    duration = format_duration(duration)

                logger.info(f"API request successful, took {time_taken}")
                return (title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url)
            else:
                logger.warning("API returned invalid data, falling back to yt-dlp")
        except Exception as e:
            logger.error(f"API request failed: {e}, falling back to yt-dlp")
    else:
        logger.info("No API token found, using yt-dlp")

    # Fallback to yt-dlp
    result = await handle_youtube_ytdlp(argument)

    # If yt-dlp fails, return error values
    if not result:
        logger.error("Both API and yt-dlp failed")
        return ("Error", "00:00", None, None, None, None, None, None)

    # Add None for stream_url since yt-dlp doesn't provide it
    return result + (None,)
