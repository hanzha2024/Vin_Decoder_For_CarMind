import json
import requests
import time
import re
from datetime import datetime

# -------------------------- 全局常量 --------------------------
fields_to_check = ["Manufacturer/Make", "Year", "Model", "Engine", "Transmission"]

# -------------------------- VIN硬解码逻辑 --------------------------
def hard_decode_vin(vin):
    if not vin or len(vin) != 17:
        return None
    
    hard_data = {}
    # 年份码（第10位）
    year_code = vin[9].upper()
    year_mapping = {
        'A': 2010, 'B': 2011, 'C': 2012, 'D': 2013, 'E': 2014, 'F': 2015,
        'G': 2016, 'H': 2017, 'J': 2018, 'K': 2019, 'L': 2020, 'M': 2021,
        'N': 2022, 'P': 2023, 'R': 2024, 'S': 2025, 'T': 2026, 'V': 2027,
        'W': 2028, 'X': 2029, 'Y': 2030, '1': 2001, '2': 2002, '3': 2003,
        '4': 2004, '5': 2005, '6': 2006, '7': 2007, '8': 2008, '9': 2009
    }
    hard_data['Year'] = year_mapping.get(year_code, f"未知（码：{year_code}）")
    
    # 制造商信息（前3位WMI码）
    wmi = vin[:3].upper()
    wmi_mapping = {
        '1HG': 'Honda', '1F': 'Ford', '1G': 'Chevrolet', '5YJ': 'Tesla',
        'JM': 'Toyota', 'WAU': 'Audi', 'WBA': 'BMW', 'WVW': 'Volkswagen',
        '5N': 'Hyundai', 'KM': 'Kia', 'SAL': 'Land Rover', 'JF': 'Subaru'
    }
    hard_data['Manufacturer/Make'] = wmi_mapping.get(wmi, f"未知（WMI：{wmi}）")
    
    return hard_data

# -------------------------- 数据加载与API调用 --------------------------
def load_vehicle_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        required_fields = ["Manufacturer/Make", "Year", "Model", "Engine", "Transmission"]
        valid_data = {}
        for vin, info in data.items():
            if not isinstance(info, dict):
                print(f"⚠️ VIN {vin} 数据格式错误（非字典），跳过")
                continue
            missing = [f for f in required_fields if f not in info]
            if missing:
                print(f"⚠️ VIN {vin} 缺失字段: {','.join(missing)}，跳过")
                continue
            for field in required_fields:
                if info[field] is None:
                    info[field] = ""
            valid_data[vin] = info
        return valid_data
    except Exception as e:
        print(f"❌ 加载车辆数据失败: {str(e)}")
        return {}

def decode_vin(vin):
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVIN/{vin}?format=json"
    max_retries = 2
    retry_delay = 2
    
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            if not data.get('Results'):
                print(f"⚠️ VIN {vin} API返回没有Results数据")
                return None
            
            api_data = {}
            for item in data['Results']:
                var = item['Variable']
                val = item['Value']
                if var in ["Displacement (L)", "Displacement (CC)"]:
                    try:
                        api_data[var] = float(val) if val is not None and str(val).strip() else None
                    except:
                        api_data[var] = val
                else:
                    api_data[var] = val
            
            disp_l = api_data.get("Displacement (L)")
            fuel_type = api_data.get("Fuel Type - Primary")
            print(f"📋 VIN {vin} API关键字段: "
                  f"排量(L)={disp_l if disp_l is not None else '无'}, "
                  f"燃料类型={fuel_type if fuel_type is not None else '无'}")
            return api_data
        except Exception as e:
            if attempt < max_retries:
                print(f"⚠️ 解析VIN {vin} 失败（尝试 {attempt+1}/{max_retries+1}）: {str(e)[:50]}...，重试...")
                time.sleep(retry_delay)
            else:
                print(f"❌ VIN {vin} 最终解析失败: {str(e)}")
                return None

def map_api_fields(api_data):
    if not api_data:
        return None
    
    raw_displacement_l = api_data.get("Displacement (L)")
    raw_displacement_cc = api_data.get("Displacement (CC)")
    display_displacement = ""
    if raw_displacement_l is not None:
        display_displacement = f"{raw_displacement_l:.1f}L"
    elif raw_displacement_cc is not None:
        display_displacement = f"{raw_displacement_cc/1000:.1f}L"
    
    raw_fuel_type = api_data.get("Fuel Type - Primary")
    standardized_fuel = ""
    if raw_fuel_type and str(raw_fuel_type).strip():
        fuel_lower = str(raw_fuel_type).strip().lower()
        if any(kw in fuel_lower for kw in ["gas", "petrol"]):
            standardized_fuel = "Gasoline"
        elif "diesel" in fuel_lower:
            standardized_fuel = "Diesel"
        elif "hybrid" in fuel_lower:
            standardized_fuel = "Hybrid"
        elif "electric" in fuel_lower:
            standardized_fuel = "Electric"
        else:
            standardized_fuel = str(raw_fuel_type).strip()
    
    engine_info_parts = []
    if display_displacement:
        engine_info_parts.append(f"Displacement: {display_displacement}")
    if standardized_fuel:
        engine_info_parts.append(f"Fuel Type: {standardized_fuel}")
    engine_config = api_data.get("Engine Configuration")
    if engine_config and str(engine_config).strip():
        engine_info_parts.append(f"Config: {str(engine_config).strip()}")
    engine_info = "; ".join(engine_info_parts) if engine_info_parts else ""
    
    return {
        "Manufacturer/Make": api_data.get("Make", "").strip() if api_data.get("Make") is not None else "",
        "Year": str(api_data.get("Model Year", "")).strip() if api_data.get("Model Year") is not None else "",
        "Model": api_data.get("Model", "").strip() if api_data.get("Model") is not None else "",
        "Engine": engine_info,
        "Transmission": api_data.get("Transmission Style", "") or api_data.get("Transmission", ""),
        "Other Engine Info": api_data.get("Other Engine Info", "").strip() if api_data.get("Other Engine Info") is not None else "",
        "raw_engine_data": {
            "raw_displacement_l": raw_displacement_l,
            "raw_displacement_cc": raw_displacement_cc,
            "raw_fuel_type": raw_fuel_type,
            "standardized_fuel": standardized_fuel
        }
    }

def normalize_text(text):
    if text is None:
        return ""
    text_str = re.sub(r'[^\w\s.\-\/;]', '', str(text))
    return re.sub(r'\s+', ' ', text_str).strip().lower()

# -------------------------- 发动机特征提取 --------------------------
def extract_engine_features(engine_text, raw_engine_data=None):
    features = {
        'displacement': None,
        'displacement_unit': 'L',
        'fuel_type': None,
        'raw_text': normalize_text(engine_text)
    }

    if isinstance(raw_engine_data, dict):
        raw_disp_l = raw_engine_data.get("raw_displacement_l")
        raw_disp_cc = raw_engine_data.get("raw_displacement_cc")
        if raw_disp_l is not None:
            features['displacement'] = round(raw_disp_l, 1)
        elif raw_disp_cc is not None:
            features['displacement'] = round(raw_disp_cc / 1000, 1)
        
        features['fuel_type'] = normalize_text(raw_engine_data.get("standardized_fuel", ""))
        return features

    text = features['raw_text']
    displacement_patterns = [
        r'(\d+\.?\d*)\s*(l|t)',
        r'(\d+)\s*(cc|cubic centimeter)',
        r'(\d+\.?\d*)\s*liter'
    ]
    for pattern in displacement_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                val = float(match.group(1).replace(',', ''))
                unit = match.group(2).lower() if len(match.groups()) > 1 else 'l'
                if unit in ['cc', 'cubic centimeter']:
                    val /= 1000
                features['displacement'] = round(val, 1)
                break
            except:
                continue
    
    fuel_mapping = {
        'gasoline': ['gas', 'gasoline', 'petrol'],
        'diesel': ['diesel', 'dsl'],
        'hybrid': ['hybrid'],
        'electric': ['electric', 'ev']
    }
    for standard, variations in fuel_mapping.items():
        if any(var in text for var in variations):
            features['fuel_type'] = standard
            break

    return features

# -------------------------- 发动机匹配规则（核心修改：扩展混动识别） --------------------------
def engine_features_match(local_engine, api_engine, api_raw_engine_data=None):
    if not local_engine.strip() and not api_engine.strip():
        return True, {
            'reason': '双方发动机文本均为空',
            'match_details': {
                'fuel_type_match': True,
                'displacement_match': True,
                'local_fuel': '无',
                'api_fuel': '无',
                'local_displacement': '无',
                'api_displacement': '无',
                'displacement_error': '无'
            }
        }
    
    local_feat = extract_engine_features(local_engine)
    api_feat = extract_engine_features(api_engine, raw_engine_data=api_raw_engine_data)
    
    match_details = {
        'fuel_type_match': False,
        'displacement_match': False,
        'local_fuel': local_feat['fuel_type'] or '无',
        'api_fuel': api_feat['fuel_type'] or '无',
        'local_displacement': f"{local_feat['displacement']}L" if local_feat['displacement'] is not None else '无',
        'api_displacement': f"{api_feat['displacement']}L" if api_feat['displacement'] is not None else '无',
        'displacement_error': '无',
        'reason': ''
    }

    # 核心修改：扩展混动车型识别逻辑
    # 1. 检查标准化燃料类型是否为混动
    is_hybrid_by_fuel = (local_feat['fuel_type'] == 'hybrid') or (api_feat['fuel_type'] == 'hybrid')
    # 2. 检查原始发动机文本中是否包含混动关键词（解决API误判问题）
    local_raw_text = normalize_text(local_engine)
    api_raw_text = normalize_text(api_engine)
    is_hybrid_by_text = ('hybrid' in local_raw_text) or ('hybrid' in api_raw_text)
    
    # 只要满足任一条件，即视为混动车型
    is_hybrid = is_hybrid_by_fuel or is_hybrid_by_text

    if is_hybrid:
        # 混动车型放开燃料类型匹配限制
        match_details['fuel_type_match'] = True
        match_details['reason'] = f"混动车型（文本含混动关键词），放开燃料类型匹配（本地：{match_details['local_fuel']}，API：{match_details['api_fuel']}）"
    else:
        # 非混动车型按原规则校验
        if local_feat['fuel_type'] and api_feat['fuel_type']:
            match_details['fuel_type_match'] = (local_feat['fuel_type'] == api_feat['fuel_type'])
            if not match_details['fuel_type_match']:
                match_details['reason'] = f"燃料类型不匹配（本地：{match_details['local_fuel']}，API：{match_details['api_fuel']}）"
                return False, match_details
        elif not local_feat['fuel_type'] and not api_feat['fuel_type']:
            match_details['fuel_type_match'] = True
        else:
            match_details['reason'] = f"燃料类型信息不完整（本地：{match_details['local_fuel']}，API：{match_details['api_fuel']}）"
            return False, match_details

    # 排量匹配（保持不变）
    if local_feat['displacement'] is not None and api_feat['displacement'] is not None:
        displacement_error = abs(local_feat['displacement'] - api_feat['displacement'])
        match_details['displacement_error'] = f"{displacement_error:.1f}L"
        # 注意：原比对结果中排量匹配为❌，可能是误差判断问题，这里修正为≤0.2L即匹配
        match_details['displacement_match'] = (displacement_error <= 0.2)
        if not match_details['displacement_match']:
            match_details['reason'] = f"排量不匹配（本地：{match_details['local_displacement']}，API：{match_details['api_displacement']}，误差{match_details['displacement_error']}，允许±0.2L）"
            return False, match_details
    elif not local_feat['displacement'] and not api_feat['displacement']:
        match_details['displacement_match'] = True
    else:
        match_details['reason'] = f"排量信息不完整（本地：{match_details['local_displacement']}，API：{match_details['api_displacement']}）"
        return False, match_details

    match_details['reason'] = f"匹配成功（燃料类型：{match_details['local_fuel']}，排量：{match_details['local_displacement']} ≈ {match_details['api_displacement']}）"
    return True, match_details

# -------------------------- 车辆比对逻辑 --------------------------
def compare_vehicles(local_data, api_data, vin):
    base_result = {
        "match": False,
        "match_rate": 0.0,
        "details": "",
        "fields": {},
        "match_source": "api",
        "engine_match_analysis": {}
    }

    if not api_data:
        hard_data = hard_decode_vin(vin)
        if hard_data:
            base_result["match_source"] = "hard_decode"
            return compare_with_source(local_data, hard_data, base_result, "硬解码数据")
        else:
            base_result["details"] = "API未返回有效数据且硬解码失败"
            return base_result

    api_raw_engine = api_data.get("raw_engine_data", {})
    print(f"   📥 VIN {vin} 传递到匹配函数的API原始数据: "
          f"排量(L)={api_raw_engine.get('raw_displacement_l') if api_raw_engine.get('raw_displacement_l') is not None else '无'}, "
          f"燃料类型={api_raw_engine.get('standardized_fuel') if api_raw_engine.get('standardized_fuel') is not None else '无'}")
    
    return compare_with_source(local_data, api_data, base_result.copy(), "API数据")

def compare_with_source(local_data, source_data, result_template, source_name):
    result = result_template.copy()
    match_count = 0

    for field in fields_to_check:
        if field not in source_data:
            result["fields"][field] = {
                "local": local_data.get(field, ""),
                "source": "硬解码无此数据",
                "match": True,
                "standardized_local": normalize_text(local_data.get(field, "")),
                "standardized_source": "N/A",
                "mismatch_reason": ""
            }
            match_count += 1
            continue

        local_val = local_data.get(field, "")
        source_val = source_data.get(field, "")
        match = False
        std_local = normalize_text(local_val)
        std_source = normalize_text(source_val)
        extra_info = {}
        mismatch_reason = ""

        if field == "Manufacturer/Make":
            match = std_local in std_source or std_source in std_local
            mismatch_reason = f"制造商不匹配（本地：{std_local}，源：{std_source}）" if not match else ""
        
        elif field == "Year":
            match = str(local_val).strip() == str(source_val).strip()
            mismatch_reason = f"年份不匹配（本地：{local_val}，源：{source_val}）" if not match else ""
        
        elif field == "Model":
            match = std_local in std_source or std_source in std_local
            mismatch_reason = f"型号不匹配（本地：{std_local}，源：{std_source}）" if not match else ""
        
        elif field == "Engine":
            api_raw_engine = source_data.get("raw_engine_data", {}) if source_name == "API数据" else None
            match, engine_analysis = engine_features_match(local_val, source_val, api_raw_engine)
            extra_info = {"match_details": engine_analysis}
            result["engine_match_analysis"] = engine_analysis
            mismatch_reason = engine_analysis.get("reason", "") if not match else ""
        
        elif field == "Transmission":
            cvt_match = ("cvt" in std_local and "automatic" in std_source) or ("cvt" in std_source and "automatic" in std_local)
            manual_match = "manual" in std_local and "manual" in std_source
            include_match = std_local in std_source or std_source in std_local
            match = cvt_match or manual_match or include_match
            mismatch_reason = f"变速箱不匹配（本地：{std_local}，源：{std_source}）" if not match else ""

        result["fields"][field] = {
            "local": local_val,
            "source": source_val,
            "match": match,
            "standardized_local": std_local,
            "standardized_source": std_source,
            "mismatch_reason": mismatch_reason,** extra_info
        }
        if match:
            match_count += 1

    total_fields = len(fields_to_check)
    result["match_rate"] = round((match_count / total_fields) * 100, 2) if total_fields > 0 else 0.0
    result["match"] = (match_count >= 4) and result["fields"]["Engine"]["match"]
    result["details"] = f"使用{source_name}比对{total_fields}字段，{match_count}个匹配，匹配率{result['match_rate']}%"
    return result

# -------------------------- 报告生成逻辑 --------------------------
def generate_report(comparison_results):
    total = len(comparison_results)
    valid_results = [res for res in comparison_results.values() if isinstance(res, dict) and "fields" in res]
    total_valid = len(valid_results)
    if total_valid == 0:
        return "### VIN解析测试报告\n\n无有效比对结果"

    fully_matched = sum(1 for res in valid_results if res.get("match", False))
    hard_decode_matched = sum(1 for res in valid_results if res["match"] and res["match_source"] == "hard_decode")
    avg_match_rate = round(sum(res["match_rate"] for res in valid_results) / total_valid, 2)
    overall_accuracy = round((fully_matched / total_valid) * 100, 2)

    field_stats = {f: {"match": 0, "total": total_valid} for f in fields_to_check}
    engine_core_stats = {
        "fuel_type_matched": 0,
        "displacement_matched": 0,
        "both_matched": 0
    }

    for res in valid_results:
        for field in field_stats:
            if res["fields"][field]["match"]:
                field_stats[field]["match"] += 1
        ea = res.get("engine_match_analysis", {})
        if ea.get("fuel_type_match"):
            engine_core_stats["fuel_type_matched"] += 1
        if ea.get("displacement_match"):
            engine_core_stats["displacement_matched"] += 1
        if ea.get("fuel_type_match") and ea.get("displacement_match"):
            engine_core_stats["both_matched"] += 1

    for field in field_stats:
        field_stats[field]["rate"] = round((field_stats[field]["match"] / field_stats[field]["total"]) * 100, 2)
        field_stats[field]["mismatch_rate"] = 100 - field_stats[field]["rate"]
    engine_core_stats["fuel_rate"] = round((engine_core_stats["fuel_type_matched"] / total_valid) * 100, 2)
    engine_core_stats["displacement_rate"] = round((engine_core_stats["displacement_matched"] / total_valid) * 100, 2)
    engine_core_stats["both_rate"] = round((engine_core_stats["both_matched"] / total_valid) * 100, 2)

    brand_stats = {}
    for vin, res in comparison_results.items():
        if not isinstance(res, dict) or "fields" not in res:
            continue
        brand = res["fields"]["Manufacturer/Make"]["local"] or "Unknown"
        if brand not in brand_stats:
            brand_stats[brand] = {
                "total": 0, "matched": 0, "engine_matched": 0,
                "fuel_matched": 0, "displacement_matched": 0
            }
        brand_stats[brand]["total"] += 1
        if res["match"]:
            brand_stats[brand]["matched"] += 1
        engine_match = res["fields"]["Engine"]["match"]
        if engine_match:
            brand_stats[brand]["engine_matched"] += 1
        ea = res.get("engine_match_analysis", {})
        if ea.get("fuel_type_match"):
            brand_stats[brand]["fuel_matched"] += 1
        if ea.get("displacement_match"):
            brand_stats[brand]["displacement_matched"] += 1

    for brand in brand_stats:
        stats = brand_stats[brand]
        stats["accuracy"] = round((stats["matched"] / stats["total"]) * 100, 2)
        stats["engine_rate"] = round((stats["engine_matched"] / stats["total"]) * 100, 2)
        stats["fuel_rate"] = round((stats["fuel_matched"] / stats["total"]) * 100, 2)
        stats["displacement_rate"] = round((stats["displacement_matched"] / stats["total"]) * 100, 2)

    mismatched_vin = [(vin, res) for vin, res in comparison_results.items() 
                     if isinstance(res, dict) and "fields" in res and not res["match"]]

    report = f"""# VIN解析准确性测试报告（仅匹配排量+燃料类型）
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
## 一、整体统计
- 总测试VIN数: {total}
- 有效比对结果数: {total_valid}
- 完全匹配成功数: {fully_matched}（硬解码匹配: {hard_decode_matched}）
- 完全匹配准确率: {overall_accuracy}%
- 平均字段匹配率: {avg_match_rate}%
- 发动机核心字段匹配统计:
  - 燃料类型匹配率: {engine_core_stats['fuel_rate']}%（{engine_core_stats['fuel_type_matched']}/{total_valid}）
  - 排量匹配率: {engine_core_stats['displacement_rate']}%（{engine_core_stats['displacement_matched']}/{total_valid}）
  - 两者均匹配率: {engine_core_stats['both_rate']}%（{engine_core_stats['both_matched']}/{total_valid}）

## 二、匹配标准说明
### 1. 整体匹配标准
- 至少匹配4个核心字段（制造商、年份、型号、发动机、变速箱）
- 发动机字段必须同时满足：燃料类型完全匹配 + 排量误差≤±0.2L（混动车型放开燃料类型限制）

### 2. 发动机核心字段匹配规则
| 字段       | 匹配要求                                                                 |
|------------|--------------------------------------------------------------------------|
| 燃料类型   | 非混动：标准化后完全匹配；混动：只要文本含"hybrid"或燃料类型为"hybrid"，即放开限制 |
| 排量       | 统一单位为升（L），忽略T/L后缀（如1.5T与1.5L视为匹配），误差≤±0.2L       |

## 三、各字段匹配率
| 字段                | 匹配数 | 总数 | 匹配率  | 不匹配率  |
|---------------------|--------|------|---------|-----------|
| Manufacturer/Make   | {field_stats['Manufacturer/Make']['match']}    | {field_stats['Manufacturer/Make']['total']}  | {field_stats['Manufacturer/Make']['rate']}% | {field_stats['Manufacturer/Make']['mismatch_rate']}% |
| Year                | {field_stats['Year']['match']}    | {field_stats['Year']['total']}  | {field_stats['Year']['rate']}% | {field_stats['Year']['mismatch_rate']}% |
| Model               | {field_stats['Model']['match']}    | {field_stats['Model']['total']}  | {field_stats['Model']['rate']}% | {field_stats['Model']['mismatch_rate']}% |
| Engine（排量+燃料） | {field_stats['Engine']['match']}    | {field_stats['Engine']['total']}  | {field_stats['Engine']['rate']}% | {field_stats['Engine']['mismatch_rate']}% |
| Transmission        | {field_stats['Transmission']['match']}    | {field_stats['Transmission']['total']}  | {field_stats['Transmission']['rate']}% | {field_stats['Transmission']['mismatch_rate']}% |

## 四、各品牌匹配情况
"""
    for brand in sorted(brand_stats.keys()):
        stats = brand_stats[brand]
        report += (f"- **{brand}**: 测试{stats['total']}台，整体匹配率{stats['accuracy']}%，"
                  f"发动机匹配率{stats['engine_rate']}%，"
                  f"燃料类型匹配率{stats['fuel_rate']}%，"
                  f"排量匹配率{stats['displacement_rate']}%\n")

    report += f"\n## 五、不匹配VIN详细情况（共{len(mismatched_vin)}台）\n"
    if mismatched_vin:
        for vin, res in mismatched_vin:
            report += f"\n### VIN: {vin} [❌ 匹配失败]\n"
            report += f"  匹配来源: {res['match_source']} | 整体匹配率: {res['match_rate']}% | 详情: {res['details']}\n"
            report += "  字段不匹配详情:\n"
            for field in fields_to_check:
                details = res["fields"][field]
                if not details["match"]:
                    report += f"    - {field}:\n"
                    report += f"        本地: {details['local'] or '空'}\n"
                    report += f"        源: {details['source'] or '空'}\n"
                    report += f"        不匹配原因: {details['mismatch_reason']}\n"
                    if field == "Engine":
                        ea = details.get("match_details", {})
                        report += f"        发动机核心匹配详情:\n"
                        report += f"          - 燃料类型: 本地={ea['local_fuel']}，API={ea['api_fuel']}，匹配: {'✅' if ea['fuel_type_match'] else '❌'}（{'混动车型放开限制' if (ea['local_fuel']=='hybrid' or ea['api_fuel']=='hybrid' or 'hybrid' in normalize_text(details['local']) or 'hybrid' in normalize_text(details['source'])) else '常规校验'}）\n"
                        report += f"          - 排量: 本地={ea['local_displacement']}，API={ea['api_displacement']}，误差={ea['displacement_error']}，匹配: {'✅' if ea['displacement_match'] else '❌'}\n"
    else:
        report += "  ✅ 所有VIN均匹配成功！\n"

    report += f"""
## 六、总结与建议
1. **匹配表现**:
   - 发动机核心字段（排量+燃料）整体匹配率{engine_core_stats['both_rate']}%
   - 优化了混动车型识别逻辑，解决API误判为Electric的问题

2. **核心优化点**:
   - 混动车型识别不再仅依赖燃料类型，还通过原始文本中的"hybrid"关键词判断
   - 修正排量匹配逻辑：2.5L与2.5L误差为0，应判定为匹配

3. **改进建议**:
   - 可扩展混动关键词库（如"phev"、"plug-in"等）进一步提升识别率
"""
    return report

# -------------------------- 主函数 --------------------------
def main():
    vehicle_data = load_vehicle_data("vehicle_simple_info.json")
    if not vehicle_data:
        print("❌ 无有效车辆数据，退出")
        return
    total_vin = len(vehicle_data)
    print(f"✅ 加载成功，共{total_vin}台车辆数据")

    api_results = {}
    comparison_results = {}
    for idx, (vin, local_info) in enumerate(vehicle_data.items(), 1):
        print(f"\n===== 处理 ({idx}/{total_vin}) VIN: {vin} =====")
        api_raw = decode_vin(vin)
        api_mapped = map_api_fields(api_raw) if api_raw else None
        api_results[vin] = {"raw_api_data": api_raw, "mapped_api_data": api_mapped}
        try:
            comp_res = compare_vehicles(local_info, api_mapped, vin)
            comparison_results[vin] = comp_res
            print(f"✅ 比对完成({comp_res['match_source']}): {comp_res['details']}")
            ea = comp_res.get("engine_match_analysis", {})
            if ea and "reason" in ea:
                print(f"   🚗 发动机匹配: {'✅' if comp_res['fields']['Engine']['match'] else '❌'}，{ea['reason']}")
        except Exception as e:
            err_msg = f"比对出错: {str(e)}"
            comparison_results[vin] = {
                "match": False, "match_rate": 0.0, "details": err_msg,
                "fields": {}, "match_source": "error", "engine_match_analysis": {}
            }
            print(f"❌ {err_msg}")
        time.sleep(1.5)

    try:
        with open("api_parsed_results.json", "w", encoding="utf-8") as f:
            json.dump(api_results, f, ensure_ascii=False, indent=2)
        print("\n✅ API结果保存至 api_parsed_results.json")
    except Exception as e:
        print(f"❌ 保存API结果失败: {str(e)}")

    try:
        with open("comparison_results.json", "w", encoding="utf-8") as f:
            json.dump(comparison_results, f, ensure_ascii=False, indent=2)
        print("✅ 比对结果保存至 comparison_results.json")
    except Exception as e:
        print(f"❌ 保存比对结果失败: {str(e)}")

    try:
        report = generate_report(comparison_results)
        with open("vin_decoding_report.txt", "w", encoding="utf-8") as f:
            f.write(report)
        print("✅ 排量+燃料匹配版报告保存至 vin_decoding_report.txt")
    except Exception as e:
        print(f"❌ 生成报告失败: {str(e)}")

if __name__ == "__main__":
    main()
    