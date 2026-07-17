import requests
from bs4 import BeautifulSoup
from email.utils import formatdate
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import time
import os
import json

def get_clean_title(text):
    if not text:
        return "Новий пост"
    
    # Беремо перший абзац (до переносу рядка)
    first_line = text.split("\n")[0].strip()
    
    if len(first_line) > 80:
        first_line = first_line[:80] + "..."
        
    return first_line if first_line else "Новий пост"

def send_to_discord(webhook_url, post_title, post_url, post_text, image_url, channel_title):
    # Формуємо основний текст повідомлення (заголовок + лінк)
    content = f"**{post_title}**\n{post_url}"
    
    if len(post_text) > 4000:
        post_text = post_text[:4000] + "..."
        
    embed = {
        "description": post_text,
        "color": 14959146, # Червоний колір Nintendo
        "author": {
            "name": channel_title
        }
    }
    
    if image_url:
        embed["thumbnail"] = {
            "url": image_url
        }
        
    payload = {
        "content": content,
        "embeds": [embed]
    }
    
    try:
        response = requests.post(
            webhook_url, 
            data=json.dumps(payload), 
            headers={"Content-Type": "application/json"}
        )
        if response.status_code not in (200, 204):
            print(f"Помилка відправки в Discord: {response.status_code}")
    except Exception as e:
        print(f"Не вдалося підключитися до Discord: {e}")

def telegram_to_fetchrss_style(channel_username, output_file="telegram_feed.xml"):
    url = f"https://t.me/s/{channel_username}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Спроби завантаження сторінки
    response = None
    for attempt in range(1, 6):
        try:
            print(f"Спроба {attempt}: завантажуємо канал @{channel_username}...")
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code == 200:
                break
            print(f"Отримано статус-код {response.status_code}. Спробуємо знову...")
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"Помилка мережі/DNS на спробі {attempt}: {e}")
            if attempt == 5:
                print("Усі 5 спроб завантаження вичерпано. Зупиняємо роботу.")
                return
            sleep_time = attempt * 5
            time.sleep(sleep_time)
            
    if not response or response.status_code != 200:
        return
        
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Ініціалізація RSS
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
    channel_title = title_tag["content"] if title_tag else f"Telegram: @{channel_username}"
    desc_tag = soup.find("meta", property="og:description")
    channel_desc = desc_tag["content"] if desc_tag else f"Telegram channel @{channel_username}"
    image_tag = soup.find("meta", property="og:image")
    channel_img_url = image_tag["content"] if image_tag else ""

    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "link").text = f"https://t.me/{channel_username}"
    ET.SubElement(channel, "description").text = channel_desc
    ET.SubElement(channel, "language").text = "uk"
    ET.SubElement(channel, "lastBuildDate").text = formatdate(usegmt=True)
    ET.SubElement(channel, "generator").text = "FetchRSS Alternative (Python)"
    ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link", {
        "href": f"https://t.me/s/{channel_username}",
        "rel": "self",
        "type": "application/rss+xml"
    })
    
    if channel_img_url:
        img_elem = ET.SubElement(channel, "image")
        ET.SubElement(img_elem, "url").text = channel_img_url
        ET.SubElement(img_elem, "title").text = channel_title
        ET.SubElement(img_elem, "link").text = f"https://t.me/{channel_username}"

    last_sent_post_id = ""
    history_file = "last_post.txt"
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            last_sent_post_id = f.read().strip()
            
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    posts = soup.find_all("div", class_="tgme_widget_message")
    parsed_posts = []
    
    for post in posts:
        if "service_message" in post.get("class", []):
            continue
            
        link_tag = post.find("a", class_="tgme_widget_message_date")
        post_link = link_tag["href"] if link_tag else f"https://t.me/{channel_username}"
        current_post_id = post.get("data-post", "").split("/")[-1]
        
        all_text_divs = post.find_all("div", class_="tgme_widget_message_text")
        text_div = None
        for div in all_text_divs:
            parent = div.parent
            is_inside_reply = False
            while parent and parent != post:
                if parent.name == "a" and "tgme_widget_message_reply" in parent.get("class", []):
                    is_inside_reply = True
                    break
                parent = parent.parent
            if not is_inside_reply:
                text_div = div
                break
        
        # === ІДЕАЛЬНИЙ УНІВЕРСАЛЬНИЙ ПОШУК КАРТИНОК ===
        img_url = None
        
        # Перебираємо абсолютно всі елементи всередині поста
        for elem in post.find_all(True):
            classes = elem.get("class", [])
            class_str = " ".join(classes).lower()
            
            # Жорстко відсікаємо аватарки каналів та емодзі
            if "user_pic" in class_str or "emoji" in class_str:
                continue
                
            # Перевірка 1: Telegram найчастіше зашиває фото в стилі 'background-image'
            if "style" in elem.attrs:
                style_str = elem["style"]
                if "background-image" in style_str:
                    match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style_str, re.I)
                    if match:
                        url_str = match.group(1)
                        # Якщо лінк починається з //, додаємо https: для Discord
                        if url_str.startswith("//"):
                            url_str = "https:" + url_str
                        img_url = url_str
                        break # Знайшли зображення — виходимо з циклу
                        
            # Перевірка 2: Рідкісні прев'ю, які Telegram віддає як звичайні <img>
            if elem.name == "img" and "src" in elem.attrs:
                url_str = elem["src"]
                # Захист від системних іконок в base64 та вбудованих емодзі
                if not url_str.startswith("data:") and "emoji" not in url_str:
                    if url_str.startswith("//"):
                        url_str = "https:" + url_str
                    img_url = url_str
                    break

        if not text_div and not img_url:
            continue
            
        html_content = ""
        plain_text = ""
        
        if img_url:
            html_content += f'<img src="{img_url}" /><br/>'
            
        if text_div:
            html_content += "".join([str(c) for c in text_div.contents])
            temp_soup = BeautifulSoup(str(text_div), "html.parser")
            
            reply_text_div = temp_soup.find(class_=re.compile(r"reply_text", re.I))
            reply_text_to_skip = ""
            if reply_text_div:
                reply_text_to_skip = reply_text_div.get_text().strip()

            for br in temp_soup.find_all("br"):
                br.replace_with("\n")
                
            plain_text = temp_soup.get_text().strip()
            
            if reply_text_to_skip:
                if plain_text.startswith(channel_title):
                    plain_text = plain_text.replace(channel_title, "", 1).strip()
                if plain_text.startswith(reply_text_to_skip):
                    plain_text = plain_text.replace(reply_text_to_skip, "", 1).strip()
        else:
            plain_text = "Медіафайл"
            
        item_title = get_clean_title(plain_text)
            
        time_tag = post.find("time")
        if time_tag and "datetime" in time_tag.attrs:
            dt = datetime.fromisoformat(time_tag["datetime"])
            pub_date = formatdate(dt.timestamp(), usegmt=True)
        else:
            pub_date = formatdate(usegmt=True)
            
        parsed_posts.append({
            "id": current_post_id,
            "title": item_title,
            "link": post_link,
            "plain_text": plain_text,
            "html_content": html_content,
            "img_url": img_url,
            "pub_date": pub_date
        })

    # ВІДПРАВКА В DISCORD
    newest_post_id = last_sent_post_id
    for p in parsed_posts:
        p_id = p["id"]
        if webhook_url and p_id:
            if not last_sent_post_id or (p_id.isdigit() and last_sent_post_id.isdigit() and int(p_id) > int(last_sent_post_id)):
                print(f"Відправляємо новий пост {p_id} в Discord по хронології...")
                send_to_discord(
                    webhook_url=webhook_url,
                    post_title=p["title"],
                    post_url=p["link"],
                    post_text=p["plain_text"],
                    image_url=p["img_url"],
                    channel_title=channel_title
                )
                time.sleep(1) # Захист від лімітів Discord
                newest_post_id = p_id

    # ЗАПИС В XML ДЛЯ RSS
    for p in reversed(parsed_posts):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = p["title"]
        ET.SubElement(item, "link").text = p["link"]
        ET.SubElement(item, "guid", isPermaLink="true").text = p["link"]
        ET.SubElement(item, "pubDate").text = p["pub_date"]
        ET.SubElement(item, "{http://purl.org/dc/elements/1.1/}creator").text = channel_title
        ET.SubElement(item, "description").text = p["html_content"]
        ET.SubElement(item, "{http://purl.org/rss/1.0/modules/content/}encoded").text = p["html_content"]
        
        if p["img_url"]:
            ET.SubElement(item, "{http://search.yahoo.com/mrss/}content", {
                "url": p["img_url"],
                "type": "image/jpeg",
                "medium": "image"
            })

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"Успішно оновлено! RSS збережено у: {output_file}")
    
    if newest_post_id:
        with open(history_file, "w") as f:
            f.write(newest_post_id)

if __name__ == "__main__":
    TARGET_CHANNEL = "ninenka" 
    telegram_to_fetchrss_style(TARGET_CHANNEL, output_file="telegram_feed.xml")