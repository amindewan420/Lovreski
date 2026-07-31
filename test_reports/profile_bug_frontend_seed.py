#!/usr/bin/env python3
"""Seed data and upload file for focused frontend profile verification."""
import base64, io, json, os, random, string
from pathlib import Path
import requests
from PIL import Image

BASE_URL = os.environ.get("BACKEND_URL", "http://localhost:8001/api")
OUT = Path('/app/test_reports/profile_bug_frontend_seed.json')
IMG_OUT = Path('/app/test_reports/frontend_large_face.jpg')
PASSWORD = 'password123'

def post(path, token=None, **kwargs):
    headers=kwargs.pop('headers', {})
    if token: headers['Authorization']=f'Bearer {token}'
    return requests.post(BASE_URL+path, headers=headers, timeout=60, **kwargs)

def put(path, token=None, **kwargs):
    headers=kwargs.pop('headers', {})
    if token: headers['Authorization']=f'Bearer {token}'
    return requests.put(BASE_URL+path, headers=headers, timeout=60, **kwargs)

def register(gender, name):
    suffix=''.join(random.choices(string.ascii_lowercase+string.digits,k=10))
    email=f"ui_profile_{suffix}@lovreski.ru"
    r=post('/auth/register', json={'email':email,'password':PASSWORD,'name':name,'gender':gender,'dob':'1998-05-15'})
    r.raise_for_status()
    d=r.json(); return d['token'], d['user'], email

def make_upload_file():
    url='https://images.unsplash.com/photo-1508214751196-bcfd4ca60f91?w=1600'
    r=requests.get(url,timeout=30,headers={'User-Agent':'Lovreski-QA/1.0'}); r.raise_for_status()
    face=Image.open(io.BytesIO(r.content)).convert('RGB')
    noise=Image.effect_noise((4000,5000),80).convert('RGB')
    face.thumbnail((1600,1600), Image.LANCZOS)
    noise.paste(face, ((noise.width-face.width)//2, (noise.height-face.height)//2))
    noise.save(IMG_OUT, format='JPEG', quality=95)
    return IMG_OUT.stat().st_size

viewer_token, viewer, viewer_email = register('female', 'Frontend Viewer')
put('/profile', token=viewer_token, json={'lat':44.95,'lng':34.10,'city':'Viewer City'})
edit_token, edit_user, edit_email = register('female', 'Frontend Edit')
put('/profile', token=edit_token, json={'photos': [], 'about':'', 'job':'', 'education':'', 'language':'', 'lat':44.95,'lng':34.10,'city':'Edit City'})

target_token, target, target_email = register('male', 'QA Full Public')
full_payload = {
    'about':'Full public about text visible to viewers.',
    'job':'QA Engineer',
    'education':'Test University',
    'language':'Russian, English',
    'height':180,
    'goal':'Long-term commitment',
    'relationship':'Single',
    'kids':'No kids',
    'smoking':"Don't smoke",
    'alcohol':'Rarely',
    'interests':['Travel','Photography','Yoga','Coffee and Tea','Books'],
    'city':'Target City',
    'lat':45.05,
    'lng':34.20,
}
r=put('/profile', token=target_token, json=full_payload); r.raise_for_status()

empty_token, empty, empty_email = register('male', 'QA Empty Public')
put('/profile', token=empty_token, json={'city':'', 'photos':[], 'lat':None, 'lng':None})
size=make_upload_file()
seed={'base_url':BASE_URL,'viewer_token':viewer_token,'viewer_user_id':viewer['user_id'],'viewer_email':viewer_email,
      'edit_token':edit_token,'edit_user_id':edit_user['user_id'],'edit_email':edit_email,
      'target_user_id':target['user_id'],'target_email':target_email,
      'empty_user_id':empty['user_id'],'empty_email':empty_email,
      'upload_file':str(IMG_OUT),'upload_file_bytes':size}
OUT.write_text(json.dumps(seed,ensure_ascii=False,indent=2), encoding='utf-8')
print(json.dumps(seed,ensure_ascii=False,indent=2))
