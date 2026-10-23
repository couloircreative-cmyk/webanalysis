from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
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

def crawl_site(start_url: u
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc
    scheme = parsed_start.scheme

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    visited = set()
    pages_data = []

    # Queue of URLs to visit (limit to homepage + up to 6 internal links)
    urls_to_visit = [start_url]
    
    start_time = time.time()
    homepage_load_time_ms = 0
    homepage_size_kb = 0

    while urls_to_visit and len(visited) < 6:
        current_url = urls_to_visit.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            req_start = time.time()
            resp = requests.get(current_url, headers=headers, timeout=8)
            req_time = int((time.time() - req_start) * 1000)

            if resp.status_code == 200:
                html = resp.text
                size_kb = len(resp.content) / 1024

                if current_url == start_url:
                    homepage_load_time_ms = req_time
                    homepage_size_kb = size_kb

                pages_data.append({"url": current_url, "html": html, "size": size_kb})

                soup = BeautifulSoup(html, 'html.parser')
                # Extract internal links for crawling
                for a_tag in soup.find_all('href' in a_tag.attrs or True and 'href' in [attr for attr in a_tag.attrs]):
                    # safer link extraction
                    pass
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    full_url = urljoin(start_url, href)
                    parsed_link = urlparse(full_url)
                    
                    # Only follow internal links
                    if parsed_link.netloc == base_domain and full_url not in visited:
                        # Skip anchor jumps, files, or login/admin pages
                        if not any(ext in full_url.lower() for ext in ['.jpg', '.png', '.pdf', '.zip', '#', 'wp-admin', 'cart', 'checkout']):
                            if full_url not in urls_to_visit:
                                urls_to_visit.append(full_url)
        except Exception:
            continue

    total_crawl_time = int((time.time() - start_time) * 1000)
    return pages_data, homepage_size_kb, homepage_load_time_ms

@app.post("/analyze")
def analyze_website(payload: AnalysisRequest):
    url = payload.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    pages, page_size_kb, load_time_ms = crawl_site(url)

    if not pages:
        raise HTTPException(status_code=400, detail="Could not reach or crawl the provided website URL.")

    # Combine text and soups across all crawled pages for deep checks
    all_text = ""
    all_forms = []
    all_images = []
    has_meta_desc = False

    for page in pages:
        soup = BeautifulSoup(page['html'], 'html.parser')
        all_text += soup.get_text().lower() + " "
        all_forms.extend(soup.find_all('form'))
        all_images.extend(soup.find_all('img'))
        
        # Check meta description on any page (prioritize homepage)
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content', '').strip():
            has_meta_desc = True

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
    c1_details = f"Homepage size: {page_size_kb:.1f} KB. Response load time: {load_time_ms}ms across {len(pages)} crawled page(s)."
    c1_suggestion = "Optimize high-resolution images, enable browser caching, and minimize heavy third-party scripts to improve speed." if c1_score < 8 else "Great load time and clean page weight."

    # ==========================================
    # CRITERIA 2: Social Proof / Testimonials
    # ==========================================
    # Broader keyword matching to ensure transparency on why points were given
    social_keywords = ['testimonial', 'review', 'what our clients say', 'customer feedback', 'rated 5 stars', 'success stories', 'trustpilot', 'case study', 'reviews', 'client results', 'endorsements']
    found_social = any(keyword in all_text for keyword in social_keywords)
    
    # Check for review class elements or schema markup
    for page in pages:
        soup = BeautifulSoup(page['html'], 'html.parser')
        if soup.find_all(class_=re.compile("testimonial|review|rating|feedback|stars", re.I)):
            found_social = True
            break

    c2_score = 10 if found_social else 3
    c2_details = "Social proof elements, review mentions, or case studies found across the crawled pages." if found_social else "No explicit reviews, testimonials, or trust badges detected in page text or CSS classes."
    c2_suggestion = "Your social proof elements were successfully detected!" if found_social else "Add a dedicated section for client testimonials, video reviews, or star ratings to build immediate trust with visitors."

    # ==========================================
    # CRITERIA 3: Forms & Quiz/Multi-step Detection
    # ==========================================
    form_count = len(all_forms)
    form_text = "".join([str(f).lower() for f in all_forms]) + all_text
    is_multi_step = any(kw in form_text for kw in ['step 1', 'quiz', 'multi-step', 'multistep', 'questionnaire', 'progress-bar', 'multi_step'])
    
    if form_count == 0:
        c3_score = 2
        c3_details = "No interactive forms found across crawled pages."
        c3_suggestion = "Add an interactive lead capture form or multi-step quote calculator to convert visitors into leads."
    elif is_multi_step or form_count >= 2:
        c3_score = 10
        c3_details = f"Found {form_count} form(s) including multi-step or quiz functionality across the site."
        c3_suggestion = "Advanced interactive forms detected, which are great for user engagement."
    else:
        c3_score = 7
        c3_details = f"Found {form_count} standard single-step form(s)."
        c3_suggestion = "Consider splitting long contact forms into a 2-step or quiz format to increase conversion rates."

    # ==========================================
    # CRITERIA 4: SEO (Alt Text & Meta Descriptions)
    # ==========================================
    total_images = len(all_images)
    images_with_alt = sum(1 for img in all_images if img.get('alt', '').strip())
    alt_ratio = (images_with_alt / total_images) if total_images > 0 else 1.0
    
    seo_score_parts = 0
    if has_meta_desc: 
        seo_score_parts += 5
    seo_score_parts += int(alt_ratio * 5)
    c4_score = max(1, seo_score_parts)
    c4_details = f"Meta description found: {'Yes'}. Image Alt Text coverage: {images_with_alt}/{total_images} images across site." if has_meta_desc else f"Meta description missing on key pages. Alt text coverage: {images_with_alt}/{total_images}."
    c4_suggestion = "Ensure every page has a unique meta description and every image includes descriptive alt text for better search rankings." if c4_score < 8 else "Solid SEO fundamentals with meta tags and image alt attributes properly configured."

    # ==========================================
    # CRITERIA 5: Contact Info (Email & Phone)
    # ==========================================
    combined_html_str = "".join([p['html'] for p in pages])
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    phone_pattern = r"(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
    
    found_emails = re.findall(email_pattern, combined_html_str)
    found_phones = re.findall(phone_pattern, combined_html_str)
    
    has_email = len(found_emails) > 0 or any('mailto:' in p['html'] for p in pages)
    has_phone = len(found_phones) > 0 or any('tel:' in p['html'] for p in pages)
    
    if has_email and has_phone:
        c5_score = 10
        c5_details = "Email address and phone number detected across the site."
        c5_suggestion = "Contact information is easily accessible."
    elif has_email or has_phone:
        c5_score = 6
        c5_details = "Partial contact info detected (either email or phone only)."
        c5_suggestion = "Add both a direct phone number and an email address in your header or footer to maximize customer trust."
    else:
        c5_score = 2
        c5_details = "No clear email address or phone number detected."
        c5_suggestion = "Include clickable phone (`tel:`) and email (`mailto:`) links in your footer so prospective clients can reach you instantly."

    # ==========================================
    # Overall Score (True out of 100)
    # ==========================================
    total_points = c1_score + c2_score + c3_score + c4_score + c5_score
    overall_score = int((total_points / 50) * 100)

    return {
        "url": url,
        "overallScore": overall_score,
        "metrics": {
            "sizeAndSpeed": {"score": c1_score, "details": c1_details, "suggestion": c1_suggestion},
            "socialProof": {"score": c2_score, "details": c2_details, "suggestion": c2_suggestion},
            "formsAndQuizzes": {"score": c3_score, "details": c3_details, "suggestion": c3_suggestion},
            "seoQuality": {"score": c4_score, "details": c4_details, "suggestion": c4_suggestion},
            "contactInfo": {"score": c5_score, "details": c5_details, "suggestion": c5_suggestion}
        }
    }
