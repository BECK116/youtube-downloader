from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import yt_dlp
import os
import asyncio
from datetime import timedelta
import humanize
import browser_cookie3

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")
templates = Jinja2Templates(directory="templates")

# 存储下载任务的状态
download_tasks = {}

def get_video_info(url):
    with yt_dlp.YoutubeDL() as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                'title': info['title'],
                'duration': str(timedelta(seconds=info['duration'])),
                'author': info['uploader'],
                'description': info['description'][:200] + '...',
                'thumbnail': info['thumbnail']
            }
        except Exception as e:
            return {'error': str(e)}

async def download_video(url):
    output_template = 'downloads/%(title)s.%(ext)s'
    ydl_opts = {
        'format': 'best',
        'outtmpl': output_template,
        'progress_hooks': [download_progress_hook],
        'cookiefile': None  # 不再需要手动指定 cookies.txt
    }
    
    # 获取 Chrome 的 cookies
    cookies = browser_cookie3.chrome(domain_name='youtube.com')
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            # 将 cookies 传递给 yt-dlp
            ydl.cookiejar = cookies
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            file_size = os.path.getsize(filename)
            return {
                'status': 'completed',
                'filename': os.path.basename(filename),
                'file_size': humanize.naturalsize(file_size),
                'info': get_video_info(url)
            }
        except Exception as e:
            return {'status': 'error', 'error': str(e)}

def download_progress_hook(d):
    if d['status'] == 'downloading':
        progress = {
            'downloaded_bytes': d.get('downloaded_bytes', 0),
            'total_bytes': d.get('total_bytes', 0),
            'speed': d.get('speed', 0),
            'eta': d.get('eta', 0)
        }
        if d['video_id'] in download_tasks:
            download_tasks[d['video_id']].update(progress)

@app.get("/")
async def home(request: Request):
    # 获取已下载的视频列表
    downloads_dir = "downloads"
    videos = []
    if os.path.exists(downloads_dir):
        for file in os.listdir(downloads_dir):
            if file.endswith(('.mp4', '.webm')):
                file_path = os.path.join(downloads_dir, file)
                file_size = humanize.naturalsize(os.path.getsize(file_path))
                videos.append({
                    'filename': file,
                    'path': f'/downloads/{file}',
                    'size': file_size
                })
    
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "videos": videos}
    )

@app.post("/download")
async def download(url: str = Form(...)):
    video_id = url.split('v=')[-1]
    download_tasks[video_id] = {'status': 'starting'}
    
    try:
        # 异步下载
        result = await download_video(url)
        download_tasks[video_id] = result
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({'status': 'error', 'error': str(e)})

@app.get("/status/{video_id}")
async def get_status(video_id: str):
    try:
        status = download_tasks.get(video_id, {'status': 'not_found'})
        return JSONResponse(status)
    except Exception as e:
        return JSONResponse({'status': 'error', 'error': str(e)})