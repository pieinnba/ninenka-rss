import requests
from bs4 import BeautifulSoup
from email.utils import formatdate
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import time
import os
import json # Потрібен для формування запиту в Discord

def get_clean_title(text):
    if not text:
        return "Новий пост"
    first_line = text.split("\n")[0].strip()
    if len(first_line) > 80:
        first_line = first_line[:80] + "..."
    return first_line if first_line else "Новий пост"

# ФУНКЦІЯ ДЛЯ ВІДПРАВКИ ПОСТУ В DISCORD
def send_to_discord(webhook_url, post_title, post_url, post_text, image_url, channel_title):
    # Формуємо основний текст повідомлення (заголовок + лінк) над ембедом
    content = f"**{post_title}**\n{post_url}"
    
    # Обрізаємо текст для ембеду, якщо він занадто довгий (ліміт Discord - 4096 символів)
    if len(post_text) > 4000:
        post_text = post_text[:4000] + "..."
        
    # Створюємо структуру Embed-повідомлення
    embed = {
        "description": post_text,           # Основний текст поста
        "color": 14959146,                  # Колір смужки зліва (червоний, під стиль Nintendo)
        "author": {
            "name": channel_title           # Ім'я автора (назва каналу) вгорі ембеду
        }
    }
    
    # Якщо в пості є картинка, додаємо її як "thumbnail" (маленька картинка справа)
    if image_url:
        embed["thumbnail"] = {
            "url": image_url
        }
        
    # Формуємо фінальний JSON-пакет для відправки
    payload = {
        "content": content,
        "embeds": [embed]
    }
    
    # Відправляємо POST-запит на Webhook
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
    
    # Блок завантаження з повторними спробами
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
    
    # Ініціалізація RSS структури
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

    # ЗЧИТУВАННЯ ІСТОРІЇ: Отримуємо ID останнього відправленого поста з файлу
    last_sent_post_id = ""
    history_file = "last_post.txt"
    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            last_sent_post_id = f.read().strip()
            
    # Дістаємо Webhook URL зі змінних оточення (які ми налаштували в GitHub Actions)
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    posts = soup.find_all("div", class_="tgme_widget_message")
    
    # Змінна для збереження найновішого ID під час цього запуску
    newest_post_id = last_sent_post_id
    
    for post in reversed(posts):
        if "service_message" in post.get("class", []):
            continue
            
        link_tag = post.find("a", class_="tgme_widget_message_date")
        post_link = link_tag["href"] if link_tag else f"https://t.me/{channel_username}"
        
        # Витягуємо унікальний ID поста (наприклад, "6000" з "ninenka/6000")
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
            temp_soup = BeautifulSoup(str(text_div), "html.parser")
            
            # Логіка очищення реплаїв (залишається такою, як була)
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
            
        # ЛОГІКА ВІДПРАВКИ В DISCORD
        # Якщо в нас є Webhook, ми знаємо ID поточного поста, 
        # і цей ID більший за останній збережений в історії (тобто пост дійсно новий)
        if webhook_url and current_post_id:
            # Використовуємо .isdigit() на випадок, якщо щось зламається і прийде не число
            if not last_sent_post_id or (current_post_id.isdigit() and last_sent_post_id.isdigit() and int(current_post_id) > int(last_sent_post_id)):
                print(f"Відправляємо новий пост {current_post_id} в Discord...")
                # Викликаємо нашу нову функцію
                send_to_discord(webhook_url, item_title, post_link, plain_text, img_url, channel_title)
                
                # Щоб не спамити Discord запитами (Rate Limit), робимо паузу 1 секунду між постами
                time.sleep(1)
                
                # Оновлюємо найновіший знайдений ID
                newest_post_id = current_post_id

    # Записуємо RSS файл
    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_file, encoding="utf-8", xml_declaration=True)
    print(f"Успішно оновлено! RSS збережено у: {output_file}")
    
    # ЗБЕРЕЖЕННЯ ІСТОРІЇ: Записуємо ID найсвіжішого поста у файл,
    # щоб наступного разу скрипт знав, з якого місця починати
    if newest_post_id:
        with open(history_file, "w") as f:
            f.write(newest_post_id)

if __name__ == "__main__":
    TARGET_CHANNEL = "ninenka" 
    telegram_to_fetchrss_style(TARGET_CHANNEL, output_file="telegram_feed.xml")