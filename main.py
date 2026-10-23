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

def crawl_site(start_url: str):
    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc

    # Enhanced headers to better mimic a real desktop browser
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }

    visited = set()
    pages_data = []
    broken_links_count = 0
    total_internal_links_checked = 0

    urls_to_visit = [start_url]
    homepage_load_time_ms = 0
    homepage_size_kb = 0

    while urls_to_visit and len(visited) < 10:
        current_url = urls_to_visit.pop(0)
        if current_url in visited:
            continue
        visited.add(current_url)

        try:
            req_start = time.time()
            # Increased timeout to 10 seconds for slower servers
            resp = requests.get(current_url, headers=headers, timeout=10)
            req_time = int((time.time() - req_start) * 1000)

            print(f"Crawled: {current_url} | Status: {resp.status_code}")

            if resp.status_code == 200:
                html = resp.text
                size_kb = len(resp.content) / 1024

                if current_url == start_url:
                    homepage_load_time_ms = req_time
                    homepage_size_kb = size_kb

                pages_data.append({"url": current_url, "html": html, "size": size_kb})

                soup = BeautifulSoup(html, 'html.parser')
                for a_tag in soup.find_all('a', href=True):
                    href = a_tag['href']
                    full_url = urljoin(start_url, href)
                    parsed_link = urlparse(full_url)
                    
                    if parsed_link.netloc == base_domain:
                        if not any(ext in full_url.lower() for ext in ['.jpg', '.png', '.pdf', '.zip', '#', 'wp-admin', 'cart', 'checkout']):
                            total_internal_links_checked += 1
                            try:
                                link_resp = requests.head(full_url, headers=headers, timeout=4)
                                if link_resp.status_code >= 400:
                                    broken_links_count += 1
                            except:
                                pass

                            if full_url not in visited and full_url not in urls_to_visit:
                                urls_to_visit.append(full_url)
        except Exception as e:
            print(f"Error crawling {current_url}: {str(e)}")
            continue

    return pages_data, homepage_size_kb, homepage_load_time_ms, broken_links_count, total_internal_links_checked

@app.post("/analyze")
def analyze_website(payload: AnalysisRequest):
    url = payload.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    pages, page_size_kb, load_time_ms, broken_links, total_links = crawl_site(url)

    if not pages:
        raise HTTPException(status_code=400, detail="Could not reach or crawl the provided website URL.")

    all_text = ""
    all_forms = []
    all_images = []
    has_meta_desc = False
    has_viewport = False
    has_og_tags = False
    has_analytics = False
    widget_indicators_found = 0
    cta_found = False

    combined_html_str = ""
    for page in pages:
        html = page['html']
        combined_html_str += html + " "
        soup = BeautifulSoup(html, 'html.parser')
        page_text = soup.get_text().lower()
        all_text += page_text + " "
        
        all_forms.extend(soup.find_all('form'))
        all_images.extend(soup.find_all('img'))
        
        # Meta description
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content', '').strip():
            has_meta_desc = True

        # Viewport tag
        if soup.find('meta', attrs={'name': 'viewport'}):
            has_viewport = True

        # Open Graph tags
        if soup.find('meta', property=re.compile("^og:", re.I)):
            has_og_tags = True

        # Analytics / Tracking Pixels
        if any(tracker in html.lower() for tracker in ['googletagmanager', 'gtag(', 'ga.js', 'facebookpixel', 'fbq(', 'hotjar', 'segment.js']):
            has_analytics = True

        # CTA buttons or keywords
        buttons = soup.find_all(['button', 'a'], class_=re.compile("btn|button|cta", re.I))
        for btn in buttons:
            btn_txt = btn.get_text().lower()
            if any(kw in btn_txt for kw in ['book', 'quote', 'schedule', 'consultation', 'get started', 'call', 'contact', 'estimate']):
                cta_found = True

        # Widgets & wizards
        if soup.find_all(['iframe', 'embed'], src=re.compile("typeform|jotform|elfsight|hubspot|calendly|surveymonkey", re.I)):
            widget_indicators_found += 1
        if soup.find_all(class_=re.compile("wizard|step|multistep|multi-step|quiz|calculator|calc|questionnaire", re.I)):
            widget_indicators_found += 1

    # ==========================================
    # 1. Size & Speed
    # ==========================================
    size_score = 10
    if page_size_kb > 4000: size_score = max(2, 10 - int((page_size_kb - 4000) / 1000))
    elif page_size_kb > 2000: size_score = 7
    elif page_size_kb > 1000: size_score = 9

    speed_score = 10 if load_time_ms <= 1500 else (7 if load_time_ms <= 3000 else 4)
    c1_score = int((size_score + speed_score) / 2)
    c1_details = f"Homepage size: {page_size_kb:.1f} KB. Response load time: {load_time_ms}ms across {len(pages)} crawled page(s)."
    c1_suggestion = "Optimize images and minimize third-party scripts to boost speed." if c1_score < 8 else "Great load time and clean page weight."

    # ==========================================
    # 2. Social Proof & Reviews
    # ==========================================
    social_keywords = ['testimonial', 'review', 'what our clients say', 'customer feedback', 'rated 5 stars', 'success stories', 'trustpilot', 'case study', 'reviews', 'client results', 'elfsight']
    found_social = any(kw in all_text for kw in social_keywords)
    c2_score = 10 if found_social else 3
    c2_details = "Social proof elements or reviews found across crawled pages." if found_social else "No explicit reviews, testimonials, or trust badges detected."
    c2_suggestion = "Add client testimonials or star ratings to build immediate trust." if c2_score < 8 else "Social proof elements successfully detected."

    # ==========================================
    # 3. Forms, Quizzes & Multi-step
    # ==========================================
    form_count = len(all_forms)
    is_multi_step = any(kw in all_text for kw in ['step 1', 'quiz', 'multi-step', 'multistep', 'questionnaire', 'wizard', 'calculator'])
    if form_count == 0 and widget_indicators_found == 0:
        c3_score, c3_details, c3_suggestion = 2, "No interactive forms found.", "Add an interactive lead capture form or calculator."
    elif is_multi_step or widget_indicators_found > 0 or form_count >= 2:
        c3_score, c3_details, c3_suggestion = 10, f"Advanced forms/quizzes detected ({form_count} form(s), {widget_indicators_found} widget(s)).", "Interactive forms are well configured."
    else:
        c3_score, c3_details, c3_suggestion = 7, f"Found {form_count} standard form(s).", "Consider splitting long forms into a multi-step wizard."

    # ==========================================
    # 4. SEO Quality (Alt Text & Meta)
    # ==========================================
    total_images = len(all_images)
    images_with_alt = sum(1 for img in all_images if img.get('alt', '').strip())
    alt_ratio = (images_with_alt / total_images) if total_images > 0 else 1.0
    c4_score = max(1, (5 if has_meta_desc else 0) + int(alt_ratio * 5))
    c4_details = f"Meta description: {'Present'}. Alt text coverage: {images_with_alt}/{total_images} images."
    c4_suggestion = "Ensure all images have alt attributes and every page has a unique meta description." if c4_score < 8 else "SEO metadata and image tags properly configured."

    # ==========================================
    # 5. Contact Info (Email & Phone)
    # ==========================================
    email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    phone_pattern = r"(\+\d{1,2}\s?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
    has_email = len(re.findall(email_pattern, combined_html_str)) > 0 or 'mailto:' in combined_html_str
    has_phone = len(re.findall(phone_pattern, combined_html_str)) > 0 or 'tel:' in combined_html_str
    
    if has_email and has_phone:
        c5_score, c5_details, c5_suggestion = 10, "Email and phone contact info detected.", "Contact info is easily accessible."
    elif has_email or has_phone:
        c5_score, c5_details, c5_suggestion = 6, "Partial contact info detected.", "Include both a direct phone number and email address."
    else:
        c5_score, c5_details, c5_suggestion = 2, "No clear email or phone number found.", "Add clickable phone and email links in your footer."

    # ==========================================
    # 6. Analytics & Tracking Pixels
    # ==========================================
    c6_score = 10 if has_analytics else 2
    c6_details = "Analytics or tracking pixels (GA4, GTM, Meta Pixel) detected." if has_analytics else "No tracking pixels or analytics tags found."
    c6_suggestion = "Install Google Tag Manager or GA4 to track visitor traffic and conversions." if c6_score < 8 else "Analytics tracking properly installed."

    # ==========================================
    # 7. Open Graph / Social Sharing Tags
    # ==========================================
    c7_score = 10 if has_og_tags else 3
    c7_details = "Open Graph social meta tags (`og:title`, `og:image`) found." if has_og_tags else "Missing Open Graph social sharing tags."
    c7_suggestion = "Add OG meta tags so your links preview correctly when shared on social media or text messages." if c7_score < 8 else "Social sharing preview tags properly configured."

    # ==========================================
    # 8. Call-to-Action (CTA) Prominence
    # ==========================================
    c8_score = 10 if cta_found else 4
    c8_details = "High-intent call-to-action buttons/links detected." if cta_found else "No clear high-intent CTA buttons found."
    c8_suggestion = "Add prominent action buttons like 'Book a Call' or 'Get a Quote' above the fold." if c8_score < 8 else "Strong call-to-action buttons present."

    # ==========================================
    # 9. Mobile Viewport Meta Tag
    # ==========================================
    c9_score = 10 if has_viewport else 1
    c9_details = "Mobile viewport meta tag present." if has_viewport else "Mobile viewport meta tag missing."
    c9_suggestion = "Add `<meta name='viewport' content='width=device-width, initial-scale=1.0'>` to ensure mobile compatibility." if c9_score < 8 else "Mobile viewport configured correctly."

    # ==========================================
    # 10. Link Health
    # ==========================================
    c10_score = 10 if broken_links == 0 else max(3, 10 - (broken_links * 2))
    c10_details = f"Checked {total_links} internal links. Broken links found: {broken_links}."
    c10_suggestion = "Fix or redirect broken internal links to improve user experience and SEO." if c10_score < 8 else "All checked internal links are healthy."

    # ==========================================
    # Overall Score (True out of 100 across 10 pillars)
    # ==========================================
    overall_score = c1_score + c2_score + c3_score + c4_score + c5_score + c6_score + c7_score + c8_score + c9_score + c10_score

    return {
        "url": url,
        "overallScore": overall_score,
        "metrics": {
            "sizeAndSpeed": {"score": c1_score, "details": c1_details, "suggestion": c1_suggestion},
            "socialProof": {"score": c2_score, "details": c2_details, "suggestion": c2_suggestion},
            "formsAndQuizzes": {"score": c3_score, "details": c3_details, "suggestion": c3_suggestion},
            "seoQuality": {"score": c4_score, "details": c4_details, "suggestion": c4_suggestion},
            "contactInfo": {"score": c5_score, "details": c5_details, "suggestion": c5_suggestion},
            "analyticsPixels": {"score": c6_score, "details": c6_details, "suggestion": c6_suggestion},
            "openGraphTags": {"score": c7_score, "details": c7_details, "suggestion": c7_suggestion},
            "ctaProminence": {"score": c8_score, "details": c8_details, "suggestion": c8_suggestion},
            "mobileViewport": {"score": c9_score, "details": c9_details, "suggestion": c9_suggestion},
            "linkHealth": {"score": c10_score, "details": c10_details, "suggestion": c10_suggestion}
        }
    }
