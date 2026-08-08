import os
import json
import time
import ssl
import io
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

# Header หลักของหน้าเว็บ
st.title("📦 ระบบถอดข้อมูลและจัดหมวดหมู่สินค้าอัตโนมัติ")
st.caption("ประมวลผลเอกสารสแกนและจัดกลุ่มสินค้าอัตโนมัติด้วย Gemini AI")
st.markdown("---")

tab1, tab2 = st.tabs(["📄 ขั้นตอนที่ 1: OCR ดึงข้อมูลจากไฟล์สแกน", "🧠 ขั้นตอนที่ 2: AI จับคู่กลุ่มสินค้า"])

# ==========================================
# TAB 1: OCR (อัปโหลดไฟล์สแกน)
# ==========================================
with tab1:
    st.subheader("1. แนบไฟล์สแกน (JPG, PNG, PDF) เพื่อทำ OCR")
    
    uploaded_scans = st.file_uploader(
        "อัปโหลดไฟล์สแกน (สามารถลากลงในช่องนี้ หรือกดเลือกหลายไฟล์พร้อมกันได้):",
        type=['jpg', 'jpeg', 'png', 'pdf', 'webp', 'bmp'],
        accept_multiple_files=True
    )

    if st.button("🚀 เริ่มอ่านไฟล์ OCR", type="primary"):
        if not uploaded_scans:
            st.warning("⚠️ กรุณาแนบไฟล์สแกนอย่างน้อย 1 ไฟล์")
        else:
            all_folder_items = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, file in enumerate(uploaded_scans):
                status_text.info(f"⏳ ({idx+1}/{len(uploaded_scans)}) กำลังอ่านไฟล์: `{file.name}`")
                
                try:
                    # ส่ง Byte ของไฟล์สแกนให้ Gemini ประมวลผลโดยตรง
                    response = client.models.generate_content(
                        model='gemini-3.5-flash-lite',
                        contents=[
                            types.Part.from_bytes(data=file.getvalue(), mime_type=file.type),
                            EXTRACTION_PROMPT
                        ],
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    items = json.loads(response.text)
                    for item in items:
                        item["ไฟล์ต้นฉบับ"] = file.name
                    all_folder_items.extend(items)
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาดกับไฟล์ {file.name}: {e}")

                progress_bar.progress((idx + 1) / len(uploaded_scans))
                if idx < len(uploaded_scans) - 1:
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

                status_text.empty()
                st.success("🎉 ประมวลผล OCR สำเร็จทุกไฟล์!")
                
                # แสดงตัวอย่างตารางผลลัพธ์
                st.dataframe(df, use_container_width=True)

                # สร้างไฟล์ Excel สำหรับดาวน์โหลดในหน่วยความจำ (BytesIO)
                buffer = io.BytesIO()
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False)
                
                st.download_button(
                    label="📥 ดาวน์โหลดไฟล์ Excel สรุปรายการสินค้า",
                    data=buffer.getvalue(),
                    file_name="สรุปรายการสินค้า.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

# ==========================================
# TAB 2: AI Mapping (แนบไฟล์ Excel 2 ไฟล์)
# ==========================================
with tab2:
    st.subheader("2. จับคู่กลุ่มสินค้าด้วย AI")
    
    col1, col2 = st.columns(2)
    with col1:
        ocr_excel = st.file_uploader("1) แนบไฟล์ Excel ผลลัพธ์ OCR (ที่ดาวน์โหลดจากขั้นตอนที่ 1)", type=['xlsx'])
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

                    # สร้างไฟล์ Excel สำหรับดาวน์โหลด
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
