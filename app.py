import os
import json
import time
import ssl
import io
import mimetypes
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
# 1. การตั้งค่าระบบ & UI Configuration
# ==========================================
st.set_page_config(
    page_title="ระบบประมวลผลเอกสารอัตโนมัติ (OCR & AI Mapping)",
    page_icon="📦",
    layout="wide"
)

# โหลด API Key จาก Streamlit Secrets
API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY)

EXTRACTION_PROMPT = """
คุณคือระบบ OCR สำหรับถอดข้อมูลรายการสินค้าจากเอกสารใบเสร็จ/ใบส่งของอย่างแม่นยำ

กฎการดึงข้อมูล:
1. ดูเฉพาะ "รายการสินค้า" เท่านั้น ข้ามข้อมูลหัวเอกสาร/ท้ายเอกสารทั้งหมด
2. รวมข้อมูลสินค้าที่ข้ามแถว: หากเอกสารแสดงข้อมูลสินค้า 1 รายการแยกหลายแถว ให้จับคู่และรวมเป็นข้อมูล 1 แถวเดียวกัน
3. หากอ่านตัวอักษร/ตัวเลขบางตัวไม่ชัด ให้ใส่ตัวที่พออ่านได้และเติมเครื่องหมาย '?' กำกับท้าย
4. ส่งผลลัพธ์กลับมาเป็น JSON Array ของ object เท่านั้น โดยใช้ Key:
   - "product_code": รหัสสินค้า (ถ้าไม่มีใส่ "")
   - "product_name": ชื่อสินค้า
   - "quantity": จำนวน (ถ้าไม่มีใส่ "")
   - "unit": หน่วย (ถ้าไม่มีใส่ "")
   - "amount": มูลค่า/ราคา (ถ้าไม่มีใส่ "")
"""

st.title("📦 ระบบถอดข้อมูลและจัดหมวดหมู่สินค้าอัตโนมัติ")
st.caption("ประมวลผลเอกสารสแกนและจัดกลุ่มสินค้าอัตโนมัติด้วย Gemini AI")
st.markdown("---")

tab1, tab2 = st.tabs(["📄 ขั้นตอนที่ 1: OCR ดึงข้อมูลจากไฟล์สแกน", "🧠 ขั้นตอนที่ 2: AI จับคู่กลุ่มสินค้า"])

# ==========================================
# TAB 1: OCR (รองรับหลายไฟล์ + ป้องกัน Error)
# ==========================================
with tab1:
    st.subheader("1. แนบไฟล์สแกน (JPG, PNG, PDF) เพื่อทำ OCR")
    
    uploaded_scans = st.file_uploader(
        "อัปโหลดไฟล์สแกน (สามารถเลือกหลายไฟล์พร้อมกันได้):",
        type=['jpg', 'jpeg', 'png', 'pdf', 'webp', 'bmp'],
        accept_multiple_files=True
    )

    if st.button("🚀 เริ่มอ่านไฟล์ OCR", type="primary"):
        if not uploaded_scans:
            st.warning("⚠️ กรุณาแนบไฟล์สแกนอย่างน้อย 1 ไฟล์")
        else:
            all_folder_items = []
            progress_bar = st.progress(0)
            status_container = st.container()

            for idx, file in enumerate(uploaded_scans):
                file_name = file.name
                
                # ตรวจสอบ MIME Type ให้ถูกต้อง
                mime_type = file.type
                if not mime_type:
                    mime_type, _ = mimetypes.guess_type(file_name)
                if not mime_type and file_name.lower().endswith('.pdf'):
                    mime_type = 'application/pdf'

                with status_container:
                    st.write(f"⏳ **({idx+1}/{len(uploaded_scans)}) กำลังประมวลผล:** `{file_name}`...")
                
                try:
                    file.seek(0)
                    file_bytes = file.getvalue()

                    response = client.models.generate_content(
                        model='gemini-3.5-flash-lite',
                        contents=[
                            types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                            EXTRACTION_PROMPT
                        ],
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )

                    # คลีนข้อความก่อนแปลง JSON
                    raw_text = response.text.strip()
                    if raw_text.startswith("```json"):
                        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                    elif raw_text.startswith("```"):
                        raw_text = raw_text.split("```")[1].split("```")[0].strip()

                    parsed_data = json.loads(raw_text)

                    # แปลงโครงสร้างข้อมูลให้เป็น List เสมอ
                    items = []
                    if isinstance(parsed_data, list):
                        items = parsed_data
                    elif isinstance(parsed_data, dict):
                        # กรณี AI ส่งกลับมาเป็น {"items": [...]} หรือ Object ตัวเดียว
                        for v in parsed_data.values():
                            if isinstance(v, list):
                                items = v
                                break
                        if not items:
                            items = [parsed_data]

                    # กำหนดชื่อไฟล์ต้นฉบับ
                    for item in items:
                        if isinstance(item, dict):
                            item["ไฟล์ต้นฉบับ"] = file_name
                            all_folder_items.append(item)

                    with status_container:
                        st.success(f"✅ `{file_name}`: ถอดข้อมูลได้ {len(items)} รายการ")

                except Exception as e:
                    with status_container:
                        st.error(f"❌ เกิดข้อผิดพลาดกับไฟล์ `{file_name}`: {e}")

                progress_bar.progress((idx + 1) / len(uploaded_scans))
                
                # หน่วงเวลาเพื่อป้องกัน Rate Limit ของ API
                if idx < len(uploaded_scans) - 1:
                    time.sleep(10)

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

                st.markdown("---")
                st.success(f"🎉 รวมข้อมูลเสร็จสิ้น! พบสินค้าทั้งหมด {len(df)} รายการ จาก {len(uploaded_scans)} ไฟล์")
                st.dataframe(df, use_container_width=True)

                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์ Excel สรุปรายการสินค้า",
                    data=buffer.getvalue(),
                    file_name="สรุปรายการสินค้า.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            else:
                st.error("❌ ไม่สามารถดึงข้อมูลรายการสินค้าจากไฟล์ที่แนบได้เลย")

# ==========================================
# TAB 2: AI Mapping
# ==========================================
with tab2:
    st.subheader("2. จับคู่กลุ่มสินค้าด้วย AI")
    
    col1, col2 = st.columns(2)
    with col1:
        ocr_excel = st.file_uploader("1) แนบไฟล์ Excel ผลลัพธ์ OCR", type=['xlsx'])
    with col2:
        ref_excel = st.file_uploader("2) แนบไฟล์ฐานข้อมูลอ้างอิง (product condition.xlsx)", type=['xlsx'])

    if st.button("🧠 เริ่มแมปกลุ่มสินค้าด้วย AI", type="primary"):
        if not ocr_excel or not ref_excel:
            st.warning("⚠️ กรุณาแนบไฟล์ให้ครบทั้ง 2 ไฟล์")
        else:
            with st.spinner("⏳ กำลังให้ AI วิเคราะห์และจับคู่กลุ่มสินค้า..."):
                try:
                    df_ocr = pd.read_excel(ocr_excel)
                    
                    if 'ชื่อสินค้า' not in df_ocr.columns:
                        st.error("❌ ไฟล์ Excel ผลลัพธ์ OCR ต้องมีคอลัมน์ 'ชื่อสินค้า'")
                        st.stop()
                        
                    unique_items = df_ocr['ชื่อสินค้า'].dropna().unique().tolist()
                    if not unique_items:
                        st.warning("⚠️ ไม่พบข้อมูลรายการชื่อสินค้าในไฟล์")
                        st.stop()

                    prompt = f"""
                    คุณคือ AI ผู้เชี่ยวชาญด้านวิเคราะห์และจับคู่ข้อมูลสินค้า
                    
                    ไฟล์ที่แนบมาด้วยคือ "ฐานข้อมูลอ้างอิง" (มีคอลัมน์ Product Name และ Item Group)
                    รายชื่อ OCR ที่ต้องวิเคราะห์:
                    {json.dumps(unique_items, ensure_ascii=False)}
                    
                    งานของคุณ:
                    ใช้การวิเคราะห์ความหมายเพื่อดูว่าสินค้า OCR แต่ละตัว น่าจะคือสินค้าใดในฐานข้อมูล แล้วดึง 'Item Group' นั้นมาตอบ
                    หากวิเคราะห์แล้วไม่เข้าข่าย Item Group ใดเลย ให้ตอบว่า "ไม่พบกลุ่มสินค้า"
                    
                    ส่งผลลัพธ์กลับมาเป็นโครงสร้าง JSON Object อย่างเดียว:
                    {{
                        "ชื่อสินค้าจาก OCR": "Item Group ที่วิเคราะห์ได้"
                    }}
                    """

                    response = client.models.generate_content(
                        model='gemini-3.5-flash-lite', 
                        contents=[
                            types.Part.from_bytes(
                                data=ref_excel.getvalue(), 
                                mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            ), 
                            prompt
                        ],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            temperature=0.1
                        )
                    )

                    ai_mapping = json.loads(response.text)
                    df_ocr['กลุ่มสินค้า (Item Group)'] = df_ocr['ชื่อสินค้า'].map(ai_mapping)

                    st.success("✅ AI จับคู่กลุ่มสินค้าเรียบร้อยแล้ว!")
                    st.dataframe(df_ocr, use_container_width=True)

                    buffer = io.BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        df_ocr.to_excel(writer, index=False)

                    st.download_button(
                        label="📥 ดาวน์โหลดไฟล์ Excel ที่แมปกลุ่มสินค้าแล้ว",
                        data=buffer.getvalue(),
                        file_name=f"AI_อัปเดต_{ocr_excel.name}",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาดในการประมวลผล: {e}")
