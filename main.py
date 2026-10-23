from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
import re
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    url: str

@app.post("/analyze")
def analyze_website(payload: AnalysisRequest):
    url = payload.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=12)
        load_time_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL. Status code: {response.status_code}")

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Connection error or invalid URL: {str(e)}")

    html_content = response.text
    soup = BeautifulSoup(html_content, 'html.parser')
    page_size_kb = len(response.content) / 1024

    # ==========================================
    # CRITERIA 1: Website Size & Speed
    # ==========================================
    size_score = 10
    if page_size_kb > 4000:
        size_score = max(2, 10 - int((page_size_kb - 4000) / 1000))
    elif page_size_kb > 2000:
        size_score = 7
    elif page_size_kb > 1000:
        size_score = 9

    speed_score = 10
    if load_time_ms > 3000:
        speed_score = 4
    elif load_time_ms > 1500:
        speed_score = 7

    c1_score = int((size_score + speed_score) / 2)
    c1_details = f"Page size: {page_size_kb:.1f} KB. Response load time: {load_time_ms}ms."

    # ==========================================
    # CRITERIA 2: Social Proof / Testimonials
    # ==========================================
    body_text = soup.get_text().lower()
    social_keywords = ['testimonial', 'review', 'what our clients say', 'customer feedback', 'rated 5 stars', 'success stories', 'trustpilot', 'case study', 'reviews']
    found_social = any(keyword in body_text for keyword in social_keywords) or bool(soup.find_all(class_=re.compile("testimonial|review|rating", re.I)))
    
    c2_score = 9 if found_social else 3
    c2_details = "Social proof elements/sections detected." if found_social else "No explicit review or testimonial sections found in the HTML structure."

    # ==========================================
    # CRITERIA 3: Forms & Quiz/Multi-step Detection
    # ==========================================
    forms = soup.find_all('form')
    form_count = len(forms)
    
    form_text = "".join([str(f).lower() for f in forms]) + body_text
    is_multi_step = any(kw in form_text for kw in ['step 1', 'quiz', 'multi-step', 'multistep', 'questionnaire', 'progress-bar'])
    
    if form_count == 0:
        c3_score = 2
        c3_details = "No interactive forms found on the page."
    elif is_multi_step or len(forms) > 2:
        c3_score = 10
        c3_details = f"Found {form_count} form(s) with multi-step or quiz indicators."
    else:
        c3_score = 7
        c3_details = f"Found {form_count} standard form(s) (single-step)."

    # ==========================================
    # CRITERIA 4: SEO (Alt Text & Meta Descriptions)
    # ==========================================
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    has_meta_desc = bool(meta_desc and meta_desc.get('content', '').strip())
    
    images = soup.find_all('img')
    total_images = len(images)
    images_with_alt = sum(1 for img in images if img.get('alt', '').strip())
    
    alt_ratio = (images_with_alt / total_images) if total_images > 0 else 1.0
    
    seo_score_parts = 0
    if has_meta_desc: 
        seo_score_parts += 5
    seo_score_parts += int(alt_ratio * 5)
    c4_score = max(1, seo_score_parts)
    c4_details = f"Meta description: {'Present' if has_meta_desc else 'Missing'}. Image Alt Text coverage: {images_with_alt}/{total_images} images."

    # ==========================================
    # CRITERIA 5: Contact Info (Email & Phone)
    # ==========================================
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    phone_pattern = r"(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
    
    found_emails = re.findall(email_pattern, html_content)
    found_phones = re.findall(phone_pattern, html_content)
    
    has_email = len(found_emails) > 0 or bool(soup.find('a', href=re.compile(r"^mailto:")))
    has_phone = len(found_phones) > 0 or bool(soup.find('a', href=re.compile(r"^tel:")))
    
    if has_email and has_phone:
        c5_score = 10
        c5_details = "Both email and phone contact info detected."
    elif has_email or has_phone:
        c5_score = 6
        c5_details = "Partial contact info detected (either email or phone only)."
    else:
        c5_score = 2
        c5_details = "No clear email or phone number detected."

    # ==========================================
    # Overall Score (True out of 100)
    # ==========================================
    # Sum of scores (max 50) multiplied by 2 to get a true 0-100 scale
    total_points = c1_score + c2_score + c3_score + c4_score + c5_score
    overall_score = int((total_points / 50) * 100)
    
    return {
        "url": url,
        "overallScore": overall_score,
        "metrics": {
            "sizeAndSpeed": {"score": c1_score, "details": c1_details},
            "socialProof": {"score": c2_score, "details": c2_details},
            "formsAndQuizzes": {"score": c3_score, "details": c3_details},
            "seoQuality": {"score": c4_score, "details": c4_details},
            "contactInfo": {"score": c5_score, "details": c5_details}
        }
    }
