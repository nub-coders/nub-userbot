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
BASE_URL = getattr(sys.modules.get('config'), 'YT_DLP_BASE_URL', os.getenv('YT_DLP_BASE_URL', 'https://api.nubcoders.com'))

def get_video_info(url_or_query: str, max_results: int = 1) -> Tuple[str, str, int, str, str, int, str, str, str]:
    """Get video info - returns (title, video_id, duration, youtube_link, channel_name, views, stream_url, thumbnail, time_taken)"""
    logger.info(f"Getting video info for: {url_or_query[:50]}{'...' if len(url_or_query) > 50 else ''}")
    try:
        logger.debug(f"Making API request to {BASE_URL}/info with max_results={max_results}")
        response = requests.get(
            f'{BASE_URL}/info',
            params={'q': url_or_query, 'max_results': max_results},
            headers={'Authorization': f'Bearer {API_TOKEN}'},
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

# Innertube API Configuration
INNERTUBE_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
INNERTUBE_CLIENT_ANDROID = {
    "clientName": "ANDROID",
    "clientVersion": "20.10.38",
    "androidSdkVersion": 30,
    "hl": "en",
    "gl": "US",
}
INNERTUBE_HEADERS_ANDROID = {
    "Content-Type": "application/json",
    "X-Youtube-Client-Name": "3",
    "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip",
}

INNERTUBE_CLIENT_VR = {
    "clientName": "ANDROID_VR",
    "clientVersion": "1.65.10",
    "deviceMake": "Oculus",
    "deviceModel": "Quest 3",
    "androidSdkVersion": 32,
    "osName": "Android",
    "osVersion": "12L",
    "hl": "en",
    "gl": "US",
}
INNERTUBE_HEADERS_VR = {
    "Content-Type": "application/json",
    "X-Youtube-Client-Name": "28",
    "User-Agent": "com.google.android.apps.youtube.vr.oculus/1.65.10 (Linux; U; Android 12L; eureka-user Build/SQ3A.220605.009.A1) gzip",
}


def extract_video_id(url_or_query: str) -> str | None:
    """Extract 11-char video ID from YouTube watch/shorts/embed URL or bare ID."""
    if not url_or_query:
        return None
    m = re.search(r"(?:v=|/shorts/|youtu\.be/|/embed/|/v/|/live/)([A-Za-z0-9_-]{11})", url_or_query)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_query.strip()):
        return url_or_query.strip()
    return None


def _post_innertube(endpoint: str, payload: dict, client: dict = INNERTUBE_CLIENT_ANDROID, headers: dict = INNERTUBE_HEADERS_ANDROID) -> dict:
    url = f"https://youtubei.googleapis.com/youtubei/v1/{endpoint}?key={INNERTUBE_KEY}"
    body = {"context": {"client": client}, **payload}
    resp = requests.post(url, json=body, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _first_video_id(node) -> tuple[str, str | None] | None:
    """Recursively search for first videoRenderer or compactVideoRenderer carrying videoId."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower().endswith("videorenderer") and isinstance(v, dict) and v.get("videoId"):
                title = None
                t_node = v.get("title")
                if isinstance(t_node, dict):
                    title = t_node.get("simpleText") or "".join(r.get("text", "") for r in t_node.get("runs", []))
                return v["videoId"], title
        for v in node.values():
            res = _first_video_id(v)
            if res:
                return res
    elif isinstance(node, list):
        for item in node:
            res = _first_video_id(item)
            if res:
                return res
    return None


def _pick_best_format(formats: list, *keys) -> dict | None:
    def rank(f):
        return tuple(("mp4" in (f.get("mimeType") or "")) if k == "mp4" else (f.get(k) or 0) for k in keys)

    valid = [f for f in formats if f.get("url")]
    return sorted(valid, key=rank)[-1] if valid else None


def pick_innertube_streams(streaming_data: dict) -> dict:
    """
    Pick best muxed (audio+video, e.g. itag 18), adaptive audio, and adaptive video stream URLs.
    """
    if not streaming_data:
        return {"stream": None, "audio": None, "video": None}

    formats = streaming_data.get("formats") or []
    adaptive = streaming_data.get("adaptiveFormats") or []

    audio_fmts = [f for f in adaptive if (f.get("mimeType") or "").startswith("audio/")]
    video_fmts = [f for f in adaptive if (f.get("mimeType") or "").startswith("video/")]

    muxed = _pick_best_format(formats, "height", "bitrate")
    best_audio = _pick_best_format(audio_fmts, "mp4", "bitrate") or muxed
    best_video = _pick_best_format(video_fmts, "mp4", "height", "bitrate") or muxed

    return {
        "stream": (muxed or {}).get("url") or (best_audio or {}).get("url"),
        "audio": (best_audio or {}).get("url"),
        "video": (best_video or {}).get("url"),
    }


def resolve_innertube(argument: str) -> tuple[str, str, str, str, str, str, str, str] | None:
    """
    Resolve YouTube metadata and muxed stream URL via direct Innertube player/search API.
    Returns: (title, duration_formatted, youtube_link, thumbnail, channel_name, views, video_id, stream_url)
    """
    try:
        vid = extract_video_id(argument)
        if not vid:
            search_resp = _post_innertube("search", {"query": argument})
            hit = _first_video_id(search_resp)
            if not hit:
                logger.warning(f"[Innertube] Search gave no results for: {argument}")
                return None
            vid = hit[0]

        # Primary: ANDROID client
        player_data = None
        try:
            player_data = _post_innertube("player", {"videoId": vid}, INNERTUBE_CLIENT_ANDROID, INNERTUBE_HEADERS_ANDROID)
        except Exception as e:
            logger.warning(f"[Innertube] ANDROID client failed for {vid}: {e}")

        # Fallback: ANDROID_VR client if primary unplayable
        ps = (player_data or {}).get("playabilityStatus") or {}
        if ps.get("status") != "OK":
            try:
                visitor = ((player_data or {}).get("responseContext") or {}).get("visitorData")
                vr_client = {**INNERTUBE_CLIENT_VR}
                if visitor:
                    vr_client["visitorData"] = visitor
                player_data = _post_innertube("player", {"videoId": vid}, vr_client, INNERTUBE_HEADERS_VR)
                ps = (player_data or {}).get("playabilityStatus") or {}
            except Exception as e:
                logger.warning(f"[Innertube] ANDROID_VR client failed for {vid}: {e}")

        if ps.get("status") != "OK":
            logger.warning(f"[Innertube] Video {vid} playability status: {ps.get('status')} - {ps.get('reason')}")
            return None

        details = player_data.get("videoDetails") or {}
        sd = player_data.get("streamingData") or {}
        picked = pick_innertube_streams(sd)
        stream_url = picked.get("stream")

        if not stream_url:
            logger.warning(f"[Innertube] No playable stream URL extracted for {vid}")
            return None

        title = details.get("title", "N/A")
        duration_sec = int(details.get("lengthSeconds", 0))
        duration_formatted = format_duration(duration_sec)
        youtube_link = f"https://www.youtube.com/watch?v={vid}"
        thumbs = (details.get("thumbnail") or {}).get("thumbnails") or []
        thumbnail_url = thumbs[-1].get("url") if thumbs else "N/A"
        channel_name = details.get("author", "N/A")
        views = details.get("viewCount", "N/A")

        logger.info(f"[Innertube] Successfully resolved stream for '{title}' ({vid})")
        return (title, duration_formatted, youtube_link, thumbnail_url, channel_name, views, vid, stream_url)
    except Exception as e:
        logger.error(f"[Innertube] Resolution exception for '{argument}': {e}")
        return None


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
    Prioritizes Innertube Muxed direct resolution, then external API calls, falls back to yt-dlp.

    Returns:
        tuple: (title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url)
    """
    # 1. Primary: Innertube direct Muxed stream resolution
    try:
        logger.info(f"Attempting Innertube direct resolution for '{argument}'...")
        innertube_result = resolve_innertube(argument)
        if innertube_result and innertube_result[7]:
            logger.info(f"Innertube resolution successful for '{argument}'")
            return innertube_result
        logger.warning("Innertube resolution returned no stream URL, trying API fallback...")
    except Exception as e:
        logger.error(f"Innertube resolution exception: {e}, trying API fallback...")

    # 2. Secondary: External API if token is available
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
                logger.warning("API returned invalid data, falling back to yt-dlp...")
        except Exception as e:
            logger.error(f"API request failed: {e}, falling back to yt-dlp...")

    logger.warning("Both Innertube and API failed, falling back to yt-dlp...")

    # 3. Fallback: yt-dlp
    result = await handle_youtube_ytdlp(argument)

    # If yt-dlp fails, return error values
    if not result:
        logger.error("Both Innertube, API, and yt-dlp failed")
        return ("Error", "00:00", None, None, None, None, None, None)

    # Add None for stream_url since yt-dlp flat extract doesn't provide it
    return result + (None,)


