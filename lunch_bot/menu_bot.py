import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

API_BASE = "https://fatraceschool.k12ea.gov.tw"

# 臺中市西區私立愛迪生幼兒園（校園食材登錄平臺）
SCHOOL_NAME = "臺中市西區愛迪生幼兒園"
KITCHEN_ID = 40553

# LINE 一次 push 最多 5 則訊息：1 則文字 + 最多 4 張菜色照片
MAX_DISH_IMAGES = 4


def fetch_day_meals(date_str):
    """date_str: 'YYYY-MM-DD'. Returns the list of meal entries (早點/午餐/午點) for that day, sorted by MenuType."""
    resp = requests.get(
        f"{API_BASE}/offering/meal",
        params={"period": f"{date_str},{date_str}", "KitchenId": KITCHEN_ID},
        timeout=15,
    )
    resp.raise_for_status()
    meals = resp.json().get("data", [])
    return sorted(meals, key=lambda m: m.get("MenuType", 0))


def fetch_dishes(batch_data_id):
    resp = requests.get(
        f"{API_BASE}/dish",
        params={"BatchDataId": batch_data_id},
        timeout=15,
    )
    resp.raise_for_status()
    dishes = resp.json().get("data", [])
    return [d for d in dishes if d.get("DishType")]


def clean_dish_name(name):
    # 每日菜名後面常附加 7 碼民國日期（例如「小米飯1150930」），移除該尾碼
    return re.sub(r"\d{7}$", "", name or "").strip()


def dish_image_url(dish_id):
    return f"{API_BASE}/dish/pic/{dish_id}"


def build_messages(display_date, meal_type_name, dishes):
    if not dishes:
        return None

    lines = [f"🍱 {display_date} {SCHOOL_NAME} {meal_type_name}"]
    for dish in dishes:
        lines.append(f"・{dish.get('DishType', '')}：{clean_dish_name(dish.get('DishName'))}")
    messages = [{"type": "text", "text": "\n".join(lines)}]

    for dish in dishes[:MAX_DISH_IMAGES]:
        dish_id = dish.get("DishId")
        if not dish_id:
            continue
        url = dish_image_url(dish_id)
        messages.append({"type": "image", "originalContentUrl": url, "previewImageUrl": url})

    return messages


def send_line_push(channel_access_token, user_id, messages):
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {channel_access_token}",
            "Content-Type": "application/json",
        },
        json={"to": user_id, "messages": messages},
        timeout=15,
    )
    resp.raise_for_status()


def main():
    channel_access_token = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
    user_id = os.environ["LINE_USER_ID"]

    # MENU_TYPE 由 GitHub Actions 依觸發的排程帶入：0=早點 1=午餐 2=午點，留空則三個都查
    menu_type_filter = os.environ.get("MENU_TYPE", "").strip()

    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    display_date = today.strftime("%Y/%m/%d")
    meals = fetch_day_meals(today.strftime("%Y-%m-%d"))

    if menu_type_filter != "":
        meals = [m for m in meals if str(m.get("MenuType")) == menu_type_filter]

    if not meals:
        print(f"{display_date} 沒有查到供餐資料（可能是假日或尚未上傳），不傳送")
        return

    for meal in meals:
        meal_type_name = meal.get("MenuTypeName", "供餐")
        dishes = fetch_dishes(meal["BatchDataId"])
        messages = build_messages(display_date, meal_type_name, dishes)

        if messages is None:
            print(f"{display_date} {meal_type_name} 沒有查到菜色資料，不傳送")
            continue

        send_line_push(channel_access_token, user_id, messages)
        print(messages[0]["text"])
        print(f"({len(messages) - 1} 張菜色照片)")

        # 避免連續呼叫觸發 LINE API 速率限制
        time.sleep(1)


if __name__ == "__main__":
    main()
