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
# 0. บังคับข้ามการตรวจสอบ SSL
# ==========================================
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. การตั้งค่าระบบ & ปรับแต่งหน้าตา UI
# ==========================================
st.set_page_config(
    page_title="ระบบประมวลผลเอกสารอัตโนมัติ (OCR & AI Mapping)",
    page_icon="📦",
    layout="wide"
)

# โหลด API Key จาก Secrets
API_KEY = st.secrets["GEMINI_API_KEY"]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, "File scan")
REF_FILE = os.path.join(SCRIPT_DIR, "product condition.xlsx")
SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.pdf', '.webp', '.bmp')

client = genai.Client(api_key=API_KEY)

EXTRACTION_PROMPT = """
คุณคือระบบ OCR สำหรับถอดข้อมูลรายการสินค้าจากเอกสารใบเสร็จ/ใบส่งของอย่างแม่นยำ

กฎการดึงข้อมูล:
1. ดูเฉพาะ "รายการสินค้า" เท่านั้น ข้ามข้อมูลหัวเอกสาร/ท้ายเอกสารทั้งหมด
2. รวมข้อมูลสินค้าที่ข้ามแถว
3. หากอ่านตัวอักษร/ตัวเลขบางตัวไม่ชัด ให้ใส่ตัวที่พออ่านได้และเติมเครื่องหมาย '?' กำกับท้าย
4. ส่งผลลัพธ์กลับมาเป็น JSON Array ของ object เท่านั้น ห้ามมีข้อความอื่น โดยใช้ Key:
   - "product_code", "product_name", "quantity", "unit", "amount"
"""

# Header หลักของหน้าเว็บ
st.title("📦 ระบบถอดข้อมูลและจัดหมวดหมู่สินค้าอัตโนมัติ")
st.caption("ระบบประมวลผลเอกสารใบส่งของ/ใบเสร็จ ด้วยเทคโนโลยี Gemini AI")
st.markdown("---")

# แบ่งการทำงานออกเป็น 2 แท็บ
tab1, tab2 = st.tabs(["📄 ขั้นตอนที่ 1: OCR ดึงข้อมูลจากไฟล์สแกน", "🧠 ขั้นตอนที่ 2: AI จับคู่กลุ่มสินค้า"])

# ==========================================
# TAB 1: OCR
# ==========================================
with tab1:
    st.subheader("1. อ่านไฟล์สแกนและแปลงเป็น Excel")
    st.info(f"📂 โฟลเดอร์ที่จะประมวลผล: `{BASE_DIR}`")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        start_ocr_btn = st.button("🚀 เริ่มอ่านไฟล์ OCR", type="primary", use_container_width=True)

    if start_ocr_btn:
        with st.spinner("⏳ กำลังค้นหาไฟล์และประมวลผล..."):
            found_any = False
            for root, dirs, files in os.walk(BASE_DIR):
                scan_files = [f for f in files if f.lower().endswith(SUPPORTED_EXTENSIONS)]
                if not scan_files:
                    continue
                
                found_any = True
                folder_name = os.path.basename(root)
                st.markdown(f"#### 📁 กำลังประมวลผลโฟลเดอร์: `{folder_name}` ({len(scan_files)} ไฟล์)")
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                all_folder_items = []

                for idx, file_name in enumerate(scan_files):
                    file_path = os.path.join(root, file_name)
                    status_text.info(f"⏳ ({idx+1}/{len(scan_files)}) กำลังอ่านไฟล์: `{file_name}`")
                    
                    try:
                        uploaded_file = client.files.upload(file=file_path)
                        response = client.models.generate_content(
                            model='gemini-3.5-flash-lite',
                            contents=[uploaded_file, EXTRACTION_PROMPT],
                            config=types.GenerateContentConfig(response_mime_type="application/json")
                        )
                        items = json.loads(response.text)
                        for item in items:
                            item["ไฟล์ต้นฉบับ"] = file_name
                        all_folder_items.extend(items)
                    except Exception as e:
                        st.error(f"❌ เกิดข้อผิดพลาดกับไฟล์ {file_name}: {e}")
                    
                    progress_bar.progress((idx + 1) / len(scan_files))
                    if idx < len(scan_files) - 1:
                        time.sleep(15)

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
                    
                    excel_path = os.path.join(root, f"สรุปรายการสินค้า_{folder_name}.xlsx")
                    df.to_excel(excel_path, index=False)
                    
                    status_text.empty()
                    st.success(f"✅ ประมวลผลโฟลเดอร์ [{folder_name}] เสร็จสมบูรณ์!")
                    
                    # แสดงตัวอย่างตารางผลลัพธ์
                    with st.expander(f"📊 ดูข้อมูลตารางสรุป ({folder_name})", expanded=True):
                        st.dataframe(df, use_container_width=True)

            if not found_any:
                st.warning("⚠️ ไม่พบไฟล์รูปภาพหรือ PDF ในโฟลเดอร์ File scan")
            else:
                st.balloons()

# ==========================================
# TAB 2: AI Mapping
# ==========================================
with tab2:
    st.subheader("2. จับคู่กลุ่มสินค้าด้วย AI")
    st.info(f"📑 ไฟล์ฐานข้อมูลอ้างอิง: `{REF_FILE}`")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        start_map_btn = st.button("🧠 เริ่มแมปกลุ่มสินค้าด้วย AI", type="primary", use_container_width=True)

    if start_map_btn:
        with st.spinner("⏳ กำลังโหลดไฟล์อ้างอิงและประมวลผล..."):
            if not os.path.exists(REF_FILE):
                st.error(f"❌ ไม่พบไฟล์อ้างอิงที่ตำแหน่ง: {REF_FILE}")
            else:
                try:
                    uploaded_ref_file = client.files.upload(file=REF_FILE)
                    st.success("✅ อัปโหลดไฟล์อ้างอิงเข้าสู่ Gemini AI สำเร็จ!")
                except Exception as e:
                    st.error(f"❌ ไม่สามารถอัปโหลดไฟล์อ้างอิงได้: {e}")
                    st.stop()

                processed_count = 0
                for root, dirs, files in os.walk(BASE_DIR):
                    for file in files:
                        if file.startswith("สรุปรายการสินค้า_") and file.endswith(".xlsx") and not file.startswith("AI_อัปเดต_"):
                            processed_count += 1
                            excel_path = os.path.join(root, file)
                            st.markdown(f"#### 🔍 กำลังวิเคราะห์ไฟล์: `{file}`")

                            try:
                                df_ocr = pd.read_excel(excel_path)
                                if 'ชื่อสินค้า' not in df_ocr.columns:
                                    st.warning(f"⚠️ ข้ามไฟล์ {file}: ไม่พบคอลัมน์ 'ชื่อสินค้า'")
                                    continue
                                    
                                unique_items = df_ocr['ชื่อสินค้า'].dropna().unique().tolist()
                                if not unique_items:
                                    continue

                                st.write(f"🧠 พบสินค้า {len(unique_items)} รายการ กำลังให้ AI เทียบหมวดหมู่...")
                                
                                prompt = f"""
                                คุณคือ AI ผู้เชี่ยวชาญด้านวิเคราะห์และจับคู่ข้อมูลสินค้า
                                ไฟล์ที่แนบมาด้วยคือ "ฐานข้อมูลอ้างอิง" (มีคอลัมน์ Product Name และ Item Group)
                                รายชื่อ OCR ที่ต้องวิเคราะห์:
                                {json.dumps(unique_items, ensure_ascii=False)}
                                
                                งานของคุณ:
                                ให้ใช้การวิเคราะห์ความหมายและความคล้ายคลึง (Semantic match) เพื่อดูว่าสินค้า OCR แต่ละตัว น่าจะคือสินค้าใดในฐานข้อมูล แล้วดึง 'Item Group' นั้นมาตอบ
                                หากวิเคราะห์แล้วไม่เข้าข่าย Item Group ใดเลยในไฟล์ ให้ตอบว่า "ไม่พบกลุ่มสินค้า"
                                
                                ส่งผลลัพธ์กลับมาเป็นโครงสร้าง JSON Object อย่างเดียว:
                                {{
                                    "ชื่อสินค้าจาก OCR": "Item Group ที่วิเคราะห์ได้"
                                }}
                                """
                                
                                response = client.models.generate_content(
                                    model='gemini-3.5-flash-lite', 
                                    contents=[uploaded_ref_file, prompt],
                                    config=types.GenerateContentConfig(
                                        response_mime_type="application/json",
                                        temperature=0.1
                                    )
                                )
                                
                                ai_mapping = json.loads(response.text)
                                df_ocr['กลุ่มสินค้า (Item Group)'] = df_ocr['ชื่อสินค้า'].map(ai_mapping)
                                
                                new_file_name = f"AI_อัปเดต_{file}"
                                new_excel_path = os.path.join(root, new_file_name)
                                df_ocr.to_excel(new_excel_path, index=False)
                                
                                st.success(f"✅ บันทึกไฟล์ที่อัปเดตแล้วเรียบร้อย: `{new_file_name}`")
                                
                                # แสดงตัวอย่างข้อมูลที่แมปแล้ว
                                with st.expander(f"📊 ดูผลลัพธ์การแมปกลุ่มสินค้า ({new_file_name})", expanded=True):
                                    st.dataframe(df_ocr, use_container_width=True)
                                
                                time.sleep(15)

                            except Exception as e:
                                st.error(f"❌ เกิดข้อผิดพลาดกับไฟล์ {file}: {e}")

                if processed_count == 0:
                    st.warning("⚠️ ไม่พบไฟล์ 'สรุปรายการสินค้า_*.xlsx' ที่รอการประมวลผล (กรุณารันขั้นตอนที่ 1 ก่อน)")
                else:
                    st.balloons()
