from googleapiclient.discovery import build
import subprocess
import json
import os
import re

API_KEY = ""

youtube = build("youtube", "v3", developerKey=API_KEY)

def get_channel_id(url):
    if "/channel/" in url:
        return url.split("/channel/")[1].split("/")[0]

    handle = url.rstrip("/").split("/")[-1]

    res = youtube.search().list(
        part="snippet",
        q=handle,
        type="channel",
        maxResults=1
    ).execute()

    if not res.get("items"):
        raise RuntimeError("Channel not found")

    return res["items"][0]["snippet"]["channelId"]

def get_video_ids(channel_id, limit):
    res = youtube.channels().list(
        part="contentDetails",
        id=channel_id
    ).execute()

    uploads = res["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    vids = []
    token = None

    while True:
        if len(vids) >= limit:
            break

        pl = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads,
            maxResults=min(50, limit - len(vids)),
            pageToken=token
        ).execute()

        for item in pl.get("items", []):
            vids.append(item["snippet"]["resourceId"]["videoId"])
            if len(vids) >= limit:
                break

        token = pl.get("nextPageToken")
        if token is None:
            break

    return vids

def get_stats(video_ids):
    data = {}

    index = 0
    while index < len(video_ids):
        batch = video_ids[index:index + 50]

        res = youtube.videos().list(
            part="snippet,statistics",
            id=",".join(batch)
        ).execute()

        for v in res.get("items", []):
            stats = v.get("statistics", {})
            data[v["id"]] = {
                "title": v["snippet"]["title"],
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0))
            }

        index += len(batch)

    return data

def clean_vtt(text):
    text = re.sub(r"<\d\d:\d\d:\d\d\.\d+>", "", text)
    text = re.sub(r"</?c>", "", text)
    text = re.sub(r">>", "", text)

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        lines.append(line)

    cleaned = []
    seen = set()

    for line in lines:
        if line not in seen:
            cleaned.append(line)
            seen.add(line)

    return " ".join(cleaned)

def get_auto_sub(video_id):
    if not os.path.exists("subs"):
        os.makedirs("subs")

    try:
        subprocess.run(
            [
                "yt-dlp",
                "--write-auto-sub",
                "--sub-lang", "en",
                "--skip-download",
                "-o", f"subs/{video_id}",
                f"https://www.youtube.com/watch?v={video_id}"
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        return

def main():
    channel_url = input("Enter YouTube channel URL: ").strip()
    limit = int(input("Enter number of videos to fetch: ").strip())

    channel_id = get_channel_id(channel_url)
    video_ids = get_video_ids(channel_id, limit)
    stats = get_stats(video_ids)

    output = []

    for i in range(len(video_ids)):
        vid = video_ids[i]
        print(f"Processing {i + 1}/{len(video_ids)}")

        get_auto_sub(vid)

        entry = {"video_id": vid}

        if vid in stats:
            entry.update(stats[vid])
        else:
            entry.update({})

        vtt_path = f"subs/{vid}.en.vtt"

        if os.path.isfile(vtt_path):
            with open(vtt_path, "r", encoding="utf-8") as f:
                text = f.read()
            entry["subtitles_en"] = clean_vtt(text)
        else:
            entry["subtitles_en"] = None

        output.append(entry)

    with open("final_output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print("Done. Saved as final_output.json")

main()
