import streamlit as st
import pandas as pd
import json
import os
import time
import tempfile
from google import genai
from google.genai import types

st.set_page_config(page_title="ระบบประมวลผลเอกสารอัตโนมัติ", layout="wide")

API_KEY = st.secrets["GEMINI_API_KEY"]
client = genai.Client(api_key=API_KEY)

EXTRACTION_PROMPT = """
คุณคือระบบ OCR สำหรับถอดข้อมูลรายการสินค้าจากเอกสารใบเสร็จ/ใบส่งของอย่างแม่นยำ

กฎการดึงข้อมูล:
1. ดูเฉพาะ "รายการสินค้า" เท่านั้น ข้ามข้อมูลหัวเอกสาร/ท้ายเอกสารทั้งหมด
2. รวมข้อมูลสินค้าที่ข้ามแถว
3. หากอ่านตัวอักษร/ตัวเลขบางตัวไม่ชัด ให้ใส่ตัวที่พออ่านได้และเติมเครื่องหมาย '?' กำกับท้าย
4. ส่งผลลัพธ์กลับมาเป็น JSON Array ของ object เท่านั้น โดยใช้ Key:
   - "product_code", "product_name", "quantity", "unit", "amount"
"""

st.title("📄 ระบบถอดข้อมูลและจัดหมวดหมู่สินค้าอัตโนมัติ (Gemini AI)")

tab1, tab2 = st.tabs(["1. อ่านเอกสาร & ดึงข้อมูล (OCR)", "2. แมปกลุ่มสินค้าด้วย AI"])

# ==========================================
# TAB 1: OCR
# ==========================================
with tab1:
    st.subheader("1. อ่านเอกสารและแปลงเป็น Excel")
    uploaded_scans = st.file_uploader(
        "อัปโหลดไฟล์สแกน (JPG, PNG, PDF)", 
        type=['jpg', 'jpeg', 'png', 'pdf', 'webp', 'bmp'], 
        accept_multiple_files=True
    )

    if st.button("🚀 เริ่มอ่านเอกสาร (OCR)", type="primary"):
        if not uploaded_scans:
            st.warning("⚠️ กรุณาอัปโหลดไฟล์สแกนอย่างน้อย 1 ไฟล์")
        else:
            all_folder_items = []
            progress_bar = st.progress(0)
            status_text = st.empty()

            for idx, file in enumerate(uploaded_scans):
                status_text.info(f"⏳ กำลังอ่านไฟล์ ({idx+1}/{len(uploaded_scans)}): {file.name}")
                
                # สร้างไฟล์ชั่วคราวเพื่ออัปโหลดเข้า Gemini
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.name)[1]) as tmp:
                    tmp.write(file.getvalue())
                    tmp_path = tmp.name

                try:
                    uploaded_file = client.files.upload(file=tmp_path)
                    response = client.models.generate_content(
                        model='gemini-3.5-flash-lite',
                        contents=[uploaded_file, EXTRACTION_PROMPT],
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    items = json.loads(response.text)
                    for item in items:
                        item["ไฟล์ต้นฉบับ"] = file.name
                    all_folder_items.extend(items)
                except Exception as e:
                    st.error(f"❌ ข้อผิดพลาดกับไฟล์ {file.name}: {e}")
                finally:
                    os.remove(tmp_path)

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
                target_cols = ["ไฟล์ต้นฉบับ", "รหัสสินค้า", "ชื่อสินค้า", "จำนวน", "หน่วย", "มูลค่า"]
                existing_cols = [c for c in target_cols if c in df.columns]
                df = df[existing_cols]

                st.success("🎉 ประมวลผลเสร็จสิ้นเรียบร้อย!")
                st.dataframe(df)

                # ปุ่มดาวน์โหลด Excel
                excel_buffer = pd.ExcelWriter("summary.xlsx", engine='openpyxl')
                df.to_excel(excel_buffer, index=False)
                excel_buffer.close()
                
                with open("summary.xlsx", "rb") as f:
                    st.download_button(
                        label="📥 ดาวน์โหลดไฟล์ Excel สรุปรายการสินค้า",
                        data=f.read(),
                        file_name="สรุปรายการสินค้า.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

# ==========================================
# TAB 2: AI Mapping
# ==========================================
with tab2:
    st.subheader("2. จับคู่และจัดกลุ่มสินค้าอัตโนมัติ")
    col1, col2 = st.columns(2)
    
    with col1:
        ocr_excel = st.file_uploader("อัปโหลดไฟล์ Excel ที่ได้จากขั้นตอนที่ 1", type=['xlsx'])
    with col2:
        ref_excel = st.file_uploader("อัปโหลดไฟล์ฐานข้อมูลอ้างอิง (product condition.xlsx)", type=['xlsx'])

    if st.button("🧠 เริ่มแมปกลุ่มสินค้าด้วย AI", type="primary"):
        if not ocr_excel or not ref_excel:
            st.warning("⚠️ กรุณาอัปโหลดไฟล์ให้ครบทั้ง 2 ไฟล์")
        else:
            with st.spinner("⏳ กำลังให้ AI วิเคราะห์และแมปข้อมูลกลุ่มสินค้า..."):
                try:
                    df_ocr = pd.read_excel(ocr_excel)
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_ref:
                        tmp_ref.write(ref_excel.getvalue())
                        tmp_ref_path = tmp_ref.name

                    uploaded_ref_file = client.files.upload(file=tmp_ref_path)
                    
                    unique_items = df_ocr['ชื่อสินค้า'].dropna().unique().tolist()
                    
                    prompt = f"""
                    คุณคือ AI ผู้เชี่ยวชาญด้านวิเคราะห์และจับคู่ข้อมูลสินค้า
                    ไฟล์ที่แนบมาด้วยคือ "ฐานข้อมูลอ้างอิง" (มีคอลัมน์ Product Name และ Item Group)
                    รายชื่อ OCR ที่ต้องวิเคราะห์:
                    {json.dumps(unique_items, ensure_ascii=False)}
                    
                    ส่งผลลัพธ์กลับมาเป็น JSON Object เท่านั้น:
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
                    
                    os.remove(tmp_ref_path)
                    
                    st.success("✅ อัปเดตกลุ่มสินค้าเรียบร้อยแล้ว!")
                    st.dataframe(df_ocr)

                    df_ocr.to_excel("ai_updated.xlsx", index=False)
                    with open("ai_updated.xlsx", "rb") as f:
                        st.download_button(
                            label="📥 ดาวน์โหลดไฟล์ Excel ที่อัปเดตกลุ่มสินค้าแล้ว",
                            data=f.read(),
                            file_name=f"AI_อัปเดต_{ocr_excel.name}",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                        
                except Exception as e:
                    st.error(f"❌ เกิดข้อผิดพลาด: {e}")
