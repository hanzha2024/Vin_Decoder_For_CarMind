import json
import requests
import re
import time

# ---------------------- Hard Decode Core Logic (VIN Structure-Based) ----------------------
def hard_decode_vin(vin):
    """
    Hard decode VIN to get Manufacturer (first 3 WMI digits) and Year (10th digit)
    Returns: dict -> {"manufacturer": hard-decoded manufacturer, "year": hard-decoded year, "decode_status": status}
    """
    # WMI (World Manufacturer Identifier) mapping - covers 10+ major brands from the test project
    wmi_mapping = {
        '1HG': 'Honda', '1F': 'Ford', '1G': 'Chevrolet', '5YJ': 'Tesla',
        'JM': 'Toyota', 'WAU': 'Audi', 'WBA': 'BMW', 'WVW': 'Volkswagen',
        'SAL': 'Land Rover', '1GY': 'Cadillac', 'KL4': 'Buick', '5T': 'Toyota',
        '3TY': 'Toyota', 'JT': 'Toyota', '4T': 'Toyota', '2HG': 'Honda',
        'JHM': 'Honda', '5F': 'Honda', '3HG': 'Honda', '1FT': 'Ford',
        '1FM': 'Ford', '1FA': 'Ford', 'WA1': 'Audi', 'WBY': 'BMW',
        '5UX': 'BMW', '7SA': 'Tesla', 'JM3': 'Mazda', '1V2': 'Volkswagen',
        '3VW': 'Volkswagen'
    }
    
    # Year code mapping (10th digit) - covers 2001-2030 (excludes invalid chars I/O/Q)
    year_mapping = {
        'A': 2010, 'B': 2011, 'C': 2012, 'D': 2013, 'E': 2014, 'F': 2015,
        'G': 2016, 'H': 2017, 'J': 2018, 'K': 2019, 'L': 2020, 'M': 2021,
        'N': 2022, 'P': 2023, 'R': 2024, 'S': 2025, 'T': 2026, 'V': 2027,
        'W': 2028, 'X': 2029, 'Y': 2030, '1': 2001, '2': 2002, '3': 2003,
        '4': 2004, '5': 2005, '6': 2006, '7': 2007, '8': 2008, '9': 2009
    }
    
    # Extract WMI and year code (VIN is already format-validated)
    wmi = vin[:3].upper()
    year_code = vin[9].upper()
    
    # Decode manufacturer
    manufacturer = wmi_mapping.get(wmi, "Hard decode unrecognized (WMI not in mapping)")
    # Decode year (convert to string for consistency with API output)
    year = year_mapping.get(year_code, "Hard decode unrecognized (Year code not in mapping)")
    if isinstance(year, int):
        year = str(year)
    
    # Determine decode status
    if manufacturer != "Hard decode unrecognized (WMI not in mapping)" and year != "Hard decode unrecognized (Year code not in mapping)":
        decode_status = "success"
    else:
        decode_status = "partial_success"
    
    return {
        "manufacturer": manufacturer,
        "year": year,
        "decode_status": decode_status
    }

# ---------------------- Core Validation & Standardization Functions ----------------------
def validate_vin(vin):
    """Validate VIN format (17 alphanumeric chars, no I/O/Q)"""
    if len(vin) != 17:
        return False, "VIN must be 17 characters long"
    invalid_chars = {'I', 'O', 'Q'}
    for char in vin:
        if char.upper() in invalid_chars:
            return False, f"VIN contains invalid character '{char}' (I/O/Q are not allowed)"
    return True, "VIN format is valid"

def extract_standardized_engine(api_raw_engine):
    """Standardize engine data to 'Displacement + Fuel Type' format from raw API engine data"""
    # 1. Process displacement (prioritize L; convert CC to L if needed)
    displacement_l = api_raw_engine.get("Displacement (L)")
    displacement_cc = api_raw_engine.get("Displacement (CC)")
    standardized_displacement = "N/A"
    
    if displacement_l is not None:
        try:
            standardized_displacement = f"{round(float(displacement_l), 1)}L"
        except:
            standardized_displacement = str(displacement_l)
    elif displacement_cc is not None:
        try:
            displacement_l_convert = round(float(displacement_cc) / 1000, 1)
            standardized_displacement = f"{displacement_l_convert}L"
        except:
            standardized_displacement = f"{displacement_cc}CC"
    
    # 2. Process fuel type (standardize to 4 categories)
    raw_fuel = api_raw_engine.get("Fuel Type - Primary", "N/A")
    standardized_fuel = "N/A"
    
    if raw_fuel and str(raw_fuel).strip():
        fuel_lower = str(raw_fuel).strip().lower()
        if any(kw in fuel_lower for kw in ["gas", "petrol", "regular unleaded", "premium unleaded"]):
            standardized_fuel = "Gasoline"
        elif "diesel" in fuel_lower:
            standardized_fuel = "Diesel"
        elif "electric" in fuel_lower:
            standardized_fuel = "Electric"
        elif "hybrid" in fuel_lower:
            standardized_fuel = "Hybrid"
        else:
            standardized_fuel = raw_fuel.strip()
    
    # 3. Format engine info (only retain displacement + fuel type)
    return f"Displacement: {standardized_displacement}; Fuel Type: {standardized_fuel}"

# ---------------------- Main VIN Decoding Function (API + Hard Decode Fallback) ----------------------
def decode_vin_simplified(vin):
    """
    Main VIN decoding function:
    - Priority 1: Use NHTSA API for full data
    - Priority 2: Fall back to hard decode if API fails/missing critical fields (Manufacturer/Year)
    Returns: dict -> {"success": bool, "vehicle_info": dict, "error": str}
    """
    # Step 1: Validate VIN format first
    vin_valid, vin_msg = validate_vin(vin)
    if not vin_valid:
        return {"success": False, "vehicle_info": {}, "error": vin_msg}
    
    # Step 2: Initialize result structure (default to hard decode fallback)
    result = {
        "success": False,
        "vehicle_info": {
            "VIN": vin.upper(),
            "Manufacturer": "N/A",
            "Year": "N/A",
            "Model": "API parsing failed, no data",
            "Engine": "API parsing failed, no data",
            "Transmission": "API parsing failed, no data",
            "Data_Source": "Hard Decode (API Unavailable)"
        },
        "error": ""
    }
    
    # Step 3: Attempt API parsing (with retries)
    api_url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVIN/{vin}?format=json"
    max_retries = 2
    retry_delay = 2
    api_success = False  # Flag to track if API returns valid data
    
    for attempt in range(max_retries + 1):
        try:
            # Send API request
            response = requests.get(api_url, timeout=15)
            response.raise_for_status()  # Trigger HTTP errors (4xx/5xx)
            api_data = response.json()
            
            # Check if API returns valid Results
            if not api_data.get("Results"):
                if attempt < max_retries:
                    print(f"API returns empty data, retrying (attempt {attempt + 1}/{max_retries + 1})...")
                    time.sleep(retry_delay)
                    continue
                else:
                    result["error"] = "API returned empty data; falling back to hard decode"
                    break
            
            # Extract and standardize API data
            parsed_info = {
                "VIN": vin.upper(),
                "Manufacturer": "N/A",
                "Year": "N/A",
                "Model": "N/A",
                "Engine": "N/A",
                "Transmission": "N/A",
                "Data_Source": "API"
            }
            api_raw_engine = {}
            
            # Map API fields to standardized structure
            for item in api_data["Results"]:
                var_name = item["Variable"]
                var_value = item["Value"] if item["Value"] is not None else "N/A"
                var_value_strip = str(var_value).strip()
                
                if var_name == "Make":
                    parsed_info["Manufacturer"] = var_value_strip if var_value_strip else "N/A"
                elif var_name == "Model Year":
                    parsed_info["Year"] = var_value_strip if var_value_strip else "N/A"
                elif var_name == "Model":
                    parsed_info["Model"] = var_value_strip if var_value_strip else "N/A"
                elif var_name in ["Transmission Style", "Transmission"]:
                    parsed_info["Transmission"] = var_value_strip if var_value_strip else "N/A"
                elif var_name in ["Displacement (L)", "Displacement (CC)", "Fuel Type - Primary"]:
                    api_raw_engine[var_name] = var_value
            
            # Standardize engine data
            parsed_info["Engine"] = extract_standardized_engine(api_raw_engine)
            
            # Further standardize fields for consistency
            # - Manufacturer: Capitalize first letter of each word
            if parsed_info["Manufacturer"] != "N/A":
                parsed_info["Manufacturer"] = parsed_info["Manufacturer"].title()
            # - Transmission: Simplify to 3 categories (CVT/Automatic/Manual)
            if "CVT" in parsed_info["Transmission"]:
                parsed_info["Transmission"] = "CVT"
            elif "Automatic" in parsed_info["Transmission"]:
                parsed_info["Transmission"] = "Automatic"
            elif "Manual" in parsed_info["Transmission"] or "Standard" in parsed_info["Transmission"]:
                parsed_info["Transmission"] = "Manual"
            
            # Step 4: Fall back to hard decode if critical fields are missing
            hard_decoded = hard_decode_vin(vin)
            if parsed_info["Manufacturer"] == "N/A":
                parsed_info["Manufacturer"] = hard_decoded["manufacturer"]
                parsed_info["Data_Source"] = "API + Hard Decode (Manufacturer补充)"  # 修正：改为"API + Hard Decode (Manufacturer补充)"→"API + Hard Decode (Manufacturer Fallback)"
                parsed_info["Data_Source"] = "API + Hard Decode (Manufacturer Fallback)"
            if parsed_info["Year"] == "N/A":
                parsed_info["Year"] = hard_decoded["year"]
                parsed_info["Data_Source"] = "API + Hard Decode (Year Fallback)"
            
            # Update result with valid API data
            result["success"] = True
            result["vehicle_info"] = parsed_info
            result["error"] = ""
            api_success = True
            break
        
        # Handle API request exceptions
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                print(f"API request timed out, retrying (attempt {attempt + 1}/{max_retries + 1})...")
                time.sleep(retry_delay)
            else:
                result["error"] = "API request timed out (2 retries exhausted); falling back to hard decode"
        except requests.exceptions.HTTPError as e:
            result["error"] = f"API HTTP Error: {str(e)[:50]}; falling back to hard decode"
            break
        except Exception as e:
            result["error"] = f"API parsing error: {str(e)[:50]}; falling back to hard decode"
            break
    
    # Step 5: If API fully fails, populate hard decode data
    if not api_success:
        hard_decoded = hard_decode_vin(vin)
        result["vehicle_info"]["Manufacturer"] = hard_decoded["manufacturer"]
        result["vehicle_info"]["Year"] = hard_decoded["year"]
        result["vehicle_info"]["Data_Source"] = "Hard Decode (API Unavailable)"
        # Mark as partially successful if hard decode gets at least one field
        result["success"] = True if hard_decoded["decode_status"] == "success" else False
    
    return result

# ---------------------- Example Usage (User-Friendly Interface) ----------------------
if __name__ == "__main__":
    print("=" * 60)
    print("                     VIN Decoding Tool (API + Hard Decode Fallback)")
    print("=" * 60)
    input_vin = input("Please enter a 17-character VIN: ").strip()
    print(f"\nDecoding VIN: {input_vin}...")
    
    # Execute decoding
    result = decode_vin_simplified(input_vin)
    
    # Print output with clean formatting
    if result["success"]:
        print("\n" + "=" * 60)
        print(f"VIN Decoding Complete | Data Source: {result['vehicle_info']['Data_Source']}")
        print("=" * 60)
        vehicle = result["vehicle_info"]
        print(f"VIN             : {vehicle['VIN']}")
        print(f"Manufacturer     : {vehicle['Manufacturer']}")
        print(f"Production Year  : {vehicle['Year']}")
        print(f"Model            : {vehicle['Model'] if vehicle['Model'] != 'N/A' else 'API parsing failed, no data'}")
        print(f"Engine (Disp+Fuel): {vehicle['Engine']}")
        print(f"Transmission     : {vehicle['Transmission'] if vehicle['Transmission'] != 'N/A' else 'API parsing failed, no data'}")
        print("=" * 60)
        if result["error"]:
            print(f"⚠️  Note: {result['error']}")
            print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("VIN Decoding Failed")
        print("=" * 60)
        print(f"❌ Error Reason: {result['error']}")
        print(f"❌ Hard Decode Status: {hard_decode_vin(input_vin)['decode_status']} (VIN may not be in hard decode mapping)")
        print("=" * 60)