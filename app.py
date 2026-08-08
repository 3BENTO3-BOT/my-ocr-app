import os
import json
import time
import ssl
import urllib3
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

# ==========================================
# 0. บังคับข้ามการตรวจสอบ SSL (กรณีติด Firewall องค์กร)
# ==========================================
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. การตั้งค่าระบบ
# ==========================================
API_KEY = st.secrets["GEMINI_API_KEY"]

# หาตำแหน่งโฟลเดอร์ปัจจุบันที่ไฟล์ .py นี้วางอยู่
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# นำมาต่อกับชื่อโฟลเดอร์และไฟล์ที่อยู่ตำแหน่งเดียวกัน
BASE_DIR = os.path.join(SCRIPT_DIR, "File scan")
REF_FILE = os.path.join(SCRIPT_DIR, "product condition.xlsx")

# นามสกุลไฟล์ที่รองรับ
SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.pdf', '.webp', '.bmp')

client = genai.Client(api_key=API_KEY)

# ==========================================
# 2. Prompt ควบคุมเงื่อนไขการถอดข้อมูล (สำหรับงานส่วนที่ 1)
# ==========================================
EXTRACTION_PROMPT = """
คุณคือระบบ OCR สำหรับถอดข้อมูลรายการสินค้าจากเอกสารใบเสร็จ/ใบส่งของอย่างแม่นยำ

กฎการดึงข้อมูล:
1. ดูเฉพาะ "รายการสินค้า" เท่านั้น ข้ามข้อมูลหัวเอกสาร/ท้ายเอกสารทั้งหมด (เช่น ชื่อบริษัท, วันที่, เลขที่เอกสาร, ยอดรวมสุทธิ)
2. รวมข้อมูลสินค้าที่ข้ามแถว: หากเอกสารแสดงข้อมูลสินค้า 1 รายการแยกหลายแถว ให้จับคู่และรวมเป็นข้อมูล 1 แถวเดียวกัน
3. หากอ่านตัวอักษร/ตัวเลขบางตัวไม่ชัด ให้ใส่ตัวที่พออ่านได้และเติมเครื่องหมาย '?' กำกับท้าย เช่น 'AB123?', '500?'
4. ส่งผลลัพธ์กลับมาเป็น JSON Array ของ object เท่านั้น ห้ามมีข้อความอื่น โดยใช้ Key ดังนี้:
   - "product_code": รหัสสินค้า (ถ้าไม่มีใส่ "")
   - "product_name": ชื่อสินค้า
   - "quantity": จำนวน (ถ้าไม่มีใส่ "")
   - "unit": หน่วย เช่น ชิ้น, กล่อง, ถุง (ถ้าไม่มีใส่ "")
   - "amount": มูลค่า/ราคา (ถ้าไม่มีใส่ "")

ตัวอย่าง JSON:
[
  {
    "product_code": "P001?",
    "product_name": "สินค้าตัวอย่าง",
    "quantity": "10",
    "unit": "ชิ้น",
    "amount": "1450.00"
  }
]
"""

# ==========================================
# 3. ฟังก์ชันงานชุดที่ 1: OCR ดึงข้อมูลจากไฟล์
# ==========================================
def extract_items_from_file(file_path):
    file_name = os.path.basename(file_path)
    print(f"  📄 กำลังอ่านไฟล์: {file_name}...")
    
    try:
        # อัปโหลดไฟล์เข้า Gemini API
        uploaded_file = client.files.upload(file=file_path)
        
        # 🌟 อัปเดต: ใช้โมเดล gemini
        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=[uploaded_file, EXTRACTION_PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        
        # แปลงข้อมูล JSON ที่ได้จาก AI
        items = json.loads(response.text)
        
        # แนบชื่อไฟล์ต้นฉบับเข้าไปในทุกแถว
        for item in items:
            item["ไฟล์ต้นฉบับ"] = file_name
            
        return items

    except Exception as e:
        print(f"  ❌ เกิดข้อผิดพลาดกับไฟล์ {file_name}: {e}")
        return []

def process_all_folders():
    print(f"🚀 เริ่มต้นการประมวลผลโฟลเดอร์หลัก: {BASE_DIR}\n")
    
    for root, dirs, files in os.walk(BASE_DIR):
        scan_files = [f for f in files if f.lower().endswith(SUPPORTED_EXTENSIONS)]
        
        if not scan_files:
            continue
            
        folder_name = os.path.basename(root)
        print(f"📁 กำลังประมวลผลโฟลเดอร์: [{folder_name}] (พบไฟล์ทั้งหมด {len(scan_files)} ไฟล์)")
        
        all_folder_items = []
        
        for file_name in scan_files:
            file_path = os.path.join(root, file_name)
            items = extract_items_from_file(file_path)
            all_folder_items.extend(items)
            
            # ⏳ ตั้งค่าหน่วงเวลา (ลดเหลือ 15 วินาทีหากใช้แพ็กเกจฟรี)
            print("⏳ พัก 15 วินาที ป้องกันการเกินโควตา API...")
            time.sleep(15) 
            
        # บันทึกเป็นไฟล์ Excel
        if all_folder_items:
            df = pd.DataFrame(all_folder_items)
            
            column_mapping = {
                "ไฟล์ต้นฉบับ": "ไฟล์ต้นฉบับ",
                "product_code": "รหัสสินค้า",
                "product_name": "ชื่อสินค้า",
                "quantity": "จำนวน",
                "unit": "หน่วย",
                "amount": "มูลค่า"
            }
            
            df = df.rename(columns=column_mapping)
            target_columns = ["ไฟล์ต้นฉบับ", "รหัสสินค้า", "ชื่อสินค้า", "จำนวน", "หน่วย", "มูลค่า"]
            existing_cols = [col for col in target_columns if col in df.columns]
            df = df[existing_cols]
            
            excel_name = f"สรุปรายการสินค้า_{folder_name}.xlsx"
            excel_path = os.path.join(root, excel_name)
            
            df.to_excel(excel_path, index=False)
            print(f"  ✨ บันทึกไฟล์ Excel สรุปเรียบร้อยที่: {excel_path}\n")
            
    print("🎉 ประมวลผลไฟล์ทั้งหมดเสร็จสิ้นแล้ว!")

# ==========================================
# 4. ฟังก์ชันงานชุดที่ 2: แมปกลุ่มสินค้าด้วย AI
# ==========================================
def ai_match_item_group():
    print("⏳ กำลังอัปโหลดไฟล์อ้างอิงให้ AI เรียนรู้เป็นฐานข้อมูล...")
    try:
        # อัปโหลดไฟล์ product condition.xlsx ให้ AI อ่าน
        uploaded_ref_file = client.files.upload(file=REF_FILE)
        print("✅ อัปโหลดไฟล์อ้างอิงสำเร็จ AI พร้อมวิเคราะห์แล้ว!\n")
    except Exception as e:
        print(f"❌ ไม่สามารถอัปโหลดไฟล์อ้างอิงได้: {e}")
        return

    print("🔍 กำลังค้นหาไฟล์ 'สรุปรายการสินค้า' ทั้งหมด...")
    
    for root, dirs, files in os.walk(BASE_DIR):
        for file in files:
            # หาไฟล์ที่ได้จากการ OCR และยังไม่ได้อัปเดตด้วย AI
            if file.startswith("สรุปรายการสินค้า_") and file.endswith(".xlsx") and not file.startswith("AI_อัปเดต_"):
                excel_path = os.path.join(root, file)
                print(f"\nกำลังประมวลผล: {file}")

                try:
                    df_ocr = pd.read_excel(excel_path)
                    
                    if 'ชื่อสินค้า' not in df_ocr.columns:
                        print("  ⚠️ ข้ามไฟล์นี้: ไม่พบคอลัมน์ 'ชื่อสินค้า'")
                        continue
                        
                    # ดึงรายชื่อสินค้าเฉพาะที่ไม่ซ้ำกันส่งให้ AI (ประหยัดเวลาและ Token)
                    unique_items = df_ocr['ชื่อสินค้า'].dropna().unique().tolist()
                    
                    if not unique_items:
                        continue

                    print(f"  🧠 กำลังให้ AI วิเคราะห์หมวดหมู่สินค้า {len(unique_items)} รายการ (ชื่อไม่เป๊ะก็หาเจอ)...")
                    
                    # เขียน Prompt สั่งงาน AI
                    prompt = f"""
                    คุณคือ AI ผู้เชี่ยวชาญด้านวิเคราะห์และจับคู่ข้อมูลสินค้า
                    
                    ไฟล์ที่แนบมาด้วยคือ "ฐานข้อมูลอ้างอิง" (มีคอลัมน์ Product Name และ Item Group)
                    ฉันมีรายชื่อสินค้าจากระบบ OCR ด้านล่างนี้ ซึ่งอาจพิมพ์ผิด พิมพ์ย่อ หรือชื่อไม่เหมือนในฐานข้อมูลเป๊ะๆ
                    
                    รายชื่อ OCR ที่ต้องวิเคราะห์:
                    {json.dumps(unique_items, ensure_ascii=False)}
                    
                    งานของคุณ:
                    ให้ใช้การวิเคราะห์ความหมายและความคล้ายคลึง (Semantic match) เพื่อดูว่าสินค้า OCR แต่ละตัว น่าจะคือสินค้าใดในฐานข้อมูล แล้วดึง 'Item Group' นั้นมาตอบ
                    หากวิเคราะห์แล้วไม่เข้าข่าย Item Group ใดเลยในไฟล์ ให้ตอบว่า "ไม่พบกลุ่มสินค้า"
                    
                    ส่งผลลัพธ์กลับมาเป็นโครงสร้าง JSON Object อย่างเดียว ห้ามมีข้อความอื่น:
                    {{
                        "ชื่อสินค้าจาก OCR รายการที่ 1": "Item Group ที่วิเคราะห์ได้",
                        "ชื่อสินค้าจาก OCR รายการที่ 2": "Item Group ที่วิเคราะห์ได้"
                    }}
                    """
                    
                    # เลือกรุ่น gemini-flash ปกติ เพราะต้องใช้ความฉลาดในการเทียบข้อมูล 3,000 กว่าบรรทัด
                    response = client.models.generate_content(
                        model='gemini-3.5-flash-lite', 
                        contents=[uploaded_ref_file, prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1 # บังคับให้ AI ไม่เดาข้อมูลมั่ว
                        )
                    )
                    
                    # แปลง JSON จาก AI กลับมาเป็นข้อมูล Python
                    ai_mapping = json.loads(response.text)
                    
                    # แมปข้อมูลกลับเข้าตาราง Excel
                    df_ocr['กลุ่มสินค้า (Item Group)'] = df_ocr['ชื่อสินค้า'].map(ai_mapping)
                    
                    # บันทึกไฟล์ใหม่โดยเติมคำว่า AI_อัปเดต_ ไว้ข้างหน้า
                    new_file_name = f"AI_อัปเดต_{file}"
                    new_excel_path = os.path.join(root, new_file_name)
                    df_ocr.to_excel(new_excel_path, index=False)
                    print(f"  ✅ วิเคราะห์เสร็จสิ้น! บันทึกไฟล์ใหม่ที่: {new_file_name}")
                    
                    # พักรอ 15 วินาที เพื่อป้องกัน API โดนบล็อก
                    print("  ⏳ พัก 15 วินาที...")
                    time.sleep(15)

                except Exception as e:
                    print(f"  ❌ เกิดข้อผิดพลาดกับไฟล์ {file}: {e}")

# ==========================================
# 5. จุดเริ่มต้นการทำงาน (รันต่อเนื่องทั้ง 2 ฟังก์ชัน)
# ==========================================
if __name__ == "__main__":
    process_all_folders()
    ai_match_item_group()
