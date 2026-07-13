import requests
from bs4 import BeautifulSoup
from email.utils import formatdate
import xml.etree.ElementTree as ET
from datetime import datetime
import re

def get_clean_title(text):
    if not text:
        return "Новий пост"
    
    # Беремо весь текст суворо до першого справжнього переходу на новий рядок
    first_line = text.split("\n")[0].strip()
    
    return first_line if first_line else "Новий пост"

def telegram_to_fetchrss_style(channel_username, output_file="telegram_feed.xml"):
    url = f"https://t.me/s/ninenka"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Помилка завантаження: {response.status_code}")
        return
        
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Реєстрація просторів імен для FetchRSS-стилю
    ET.register_namespace('content', 'http://purl.org/rss/1.0/modules/content/')
    ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
    ET.register_namespace('media', 'http://search.yahoo.com/mrss/')
    ET.register_namespace('atom', 'http://www.w3.org/2005/Atom')
    
    rss = ET.Element("rss", {
        "version": "2.0",
        "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
        "xmlns:dc": "http://purl.org/dc/elements/1.1/",
        "xmlns:media": "http://search.yahoo.com/mrss/",
        "xmlns:atom": "http://www.w3.org/2005/Atom"
    })
    
    channel = ET.SubElement(rss, "channel")
    
    title_tag = soup.find("meta", property="og:title")
    channel_title = title_tag["content"] if title_tag else f"Telegram: @ninenka"
    
    desc_tag = soup.find("meta", property="og:description")
    channel_desc = desc_tag["content"] if desc_tag else f"Telegram channel @ninenka"
    
    image_tag = soup.find("meta", property="og:image")
    channel_img_url = image_tag["content"] if image_tag else ""

    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = f"https://t.me/ninenka"
    ET.SubElement(channel, "description").text = channel_desc
    ET.SubElement(channel, "language").text = "uk"
    ET.SubElement(channel, "lastBuildDate").text = formatdate(usegmt=True)
    ET.SubElement(channel, "generator").text = "FetchRSS Alternative (Python)"
    
    ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link", {
        "href": f"https://t.me/s/ninenka",
        "rel": "self",
        "type": "application/rss+xml"
    })
    
    if channel_img_url:
        img_elem = ET.SubElement(channel, "image")
        ET.SubElement(img_elem, "url").text = channel_img_url
        ET.SubElement(img_elem, "title").text = channel_title
        ET.SubElement(img_elem, "link").text = f"https://t.me/ninenka"

    posts = soup.find_all("div", class_="tgme_widget_message")
    
    for post in reversed(posts):
        if "service_message" in post.get("class", []):
            continue
            
        link_tag = post.find("a", class_="tgme_widget_message_date")
        post_link = link_tag["href"] if link_tag else f"https://t.me/ninenka"
        
        text_div = post.find("div", class_="tgme_widget_message_text")
        
        img_url = None
        photo_wrap = post.find("a", class_="tgme_widget_message_photo_wrap")
        if photo_wrap and "style" in photo_wrap.attrs:
            style_str = photo_wrap["style"]
            match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style_str)
            if match:
                img_url = match.group(1)
        
        if not text_div and not img_url:
            continue
            
        html_content = ""
        plain_text = ""
        
        if img_url:
            html_content += f'<img src="{img_url}" /><br/>'
            
        if text_div:
            html_content += "".join([str(c) for c in text_div.contents])
            
            # Створюємо ізольовану копію тексту для очищення заголовка
            temp_soup = BeautifulSoup(str(text_div), "html.parser")
            
            # ФІКС ТУТ: Знаходимо і видаляємо блоки цитування відповідей (наприклад, .tgme_widget_message_reply)
            for reply_block in temp_soup.find_all(class_=re.compile(r"reply")):
                reply_block.decompose()
            
            for br in temp_soup.find_all("br"):
                br.replace_with("\n")
            
            plain_text = temp_soup.get_text()
        else:
            plain_text = "Зображення"
            
        item_title = get_clean_title(plain_text)
            
        time_tag = post.find("time")
        if time_tag and "datetime" in time_tag.attrs:
            dt = datetime.fromisoformat(time_tag["datetime"])
            pub_date = formatdate(dt.timestamp(), usegmt=True)
        else:
            pub_date = formatdate(usegmt=True)
            
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = item_title
        ET.SubElement(item, "link").text = post_link
        ET.SubElement(item, "guid", isPermaLink="true").text = post_link
        ET.SubElement(item, "pubDate").text = pub_date
        
        ET.SubElement(item, "{http://purl.org/dc/elements/1.1/}creator").text = channel_title
        ET.SubElement(item, "description").text = html_content
        ET.SubElement(item, "{http://purl.org/rss/1.0/modules/content/}encoded").text = html_content
        
        if img_url:
            ET.SubElement(item, "{http://search.yahoo.com/mrss/}content", {
                "url": img_url,
                "type": "image/jpeg",
                "medium": "image"
            })

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"Готово! Заголовки очищено від реплаїв. Файл збережено у: {output_file}")

if __name__ == "__main__":
    TARGET_CHANNEL = "ninenka" 
    telegram_to_fetchrss_style(TARGET_CHANNEL, output_file="telegram_feed.xml")