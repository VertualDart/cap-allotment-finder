#!/usr/bin/env python3
"""
DSE CET Allotment Search Script
Searches through CAP1 and CAP2 allotment PDFs for a given name
"""

import os
import re
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin
import PyPDF2
from io import BytesIO
from bs4 import BeautifulSoup

class DSEAllotmentSearcher:
    def __init__(self):
        self.base_url = "https://dse2025.mahacet.org.in/dse25/"
        self.index_url = "https://dse2025.mahacet.org.in/dse25/index.php/hp_controller/instwiseallotment"
        self.pdf_dir = "dse_pdfs"
        self.colleges_data = {}
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Create directory for PDFs
        os.makedirs(self.pdf_dir, exist_ok=True)
        os.makedirs(f"{self.pdf_dir}/cap1", exist_ok=True)
        os.makedirs(f"{self.pdf_dir}/cap2", exist_ok=True)

    def scrape_college_data(self):
        """Scrape the index page to get college names and codes"""
        print("Fetching college data from index page...")
        
        try:
            response = self.session.get(self.index_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find table rows with college data
            rows = soup.find_all('tr')
            
            for row in rows[1:]:  # Skip header row
                cells = row.find_all('td')
                if len(cells) >= 3:
                    try:
                        sr_no = cells[0].get_text(strip=True)
                        institute_code = cells[1].get_text(strip=True)
                        institute_name = cells[2].get_text(strip=True)
                        
                        # Skip non-numeric rows
                        if not institute_code.isdigit():
                            continue
                            
                        self.colleges_data[institute_code] = {
                            'sr_no': sr_no,
                            'name': institute_name,
                            'code': institute_code
                        }
                    except (IndexError, ValueError):
                        continue
            
            print(f"Found {len(self.colleges_data)} colleges")
            return True
            
        except Exception as e:
            print(f"Error scraping college data: {e}")
            print("Using fallback institute codes...")
            # Fallback: use common institute code patterns
            self.generate_fallback_codes()
            return False

    def generate_fallback_codes(self):
        """Generate fallback institute codes based on common patterns"""
        # Based on the pattern observed in the HTML
        code_ranges = [
            range(1002, 1300),  # Amravati region
            range(2008, 2800),  # Aurangabad region  
            range(3012, 3600),  # Mumbai region
            range(4004, 4800),  # Nagpur region
            range(5003, 5600),  # North Maharashtra
            range(6004, 7000),  # Pune region
            range(14005, 14006), # Special codes
            range(16006, 16200)  # Special codes
        ]
        
        for code_range in code_ranges:
            for code in code_range:
                self.colleges_data[str(code)] = {
                    'sr_no': '',
                    'name': f'Institute {code}',
                    'code': str(code)
                }

    def download_pdf(self, institute_code, cap_round):
        """Download a single PDF file"""
        pdf_url = f"{self.base_url}admin/allotment/{cap_round}/{institute_code}_4.pdf"
        local_path = f"{self.pdf_dir}/{cap_round}/{institute_code}_4.pdf"
        
        # Skip if already downloaded
        if os.path.exists(local_path):
            return local_path, True, "Already exists"
        
        try:
            response = self.session.get(pdf_url, timeout=30)
            response.raise_for_status()
            
            # Check if response is actually a PDF
            if 'application/pdf' in response.headers.get('content-type', ''):
                with open(local_path, 'wb') as f:
                    f.write(response.content)
                return local_path, True, "Downloaded"
            else:
                return local_path, False, "Not a PDF"
                
        except requests.exceptions.RequestException as e:
            return local_path, False, f"Error: {str(e)[:50]}"

    def download_all_pdfs(self, max_workers=5):
        """Download all PDFs with threading"""
        print("Starting PDF downloads...")
        
        download_tasks = []
        for institute_code in self.colleges_data.keys():
            download_tasks.append((institute_code, 'cap1'))
            download_tasks.append((institute_code, 'cap2'))
        
        successful_downloads = 0
        failed_downloads = 0
        already_exists = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_task = {
                executor.submit(self.download_pdf, code, cap): (code, cap)
                for code, cap in download_tasks
            }
            
            for future in as_completed(future_to_task):
                code, cap = future_to_task[future]
                try:
                    path, success, message = future.result()
                    if success and "Already exists" in message:
                        already_exists += 1
                    elif success:
                        successful_downloads += 1
                        print(f"✓ Downloaded {cap.upper()}: {code}")
                    else:
                        failed_downloads += 1
                        if "404" not in message:  # Don't spam 404 errors
                            print(f"✗ Failed {cap.upper()}: {code} - {message}")
                except Exception as e:
                    failed_downloads += 1
                    print(f"✗ Exception for {code} {cap}: {e}")
        
        print(f"\nDownload Summary:")
        print(f"Successful downloads: {successful_downloads}")
        print(f"Already existed: {already_exists}")
        print(f"Failed downloads: {failed_downloads}")

    def search_pdf(self, pdf_path, search_name):
        """Search for a name in a PDF file"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                full_text = ""
                
                for page in pdf_reader.pages:
                    full_text += page.extract_text() + "\n"
                
                # Case-insensitive search
                if search_name.lower() in full_text.lower():
                    # Find the line containing the name for context
                    lines = full_text.split('\n')
                    matching_lines = [line.strip() for line in lines 
                                    if search_name.lower() in line.lower() and line.strip()]
                    return True, matching_lines[:3]  # Return up to 3 matching lines
                return False, []
                
        except Exception as e:
            return False, [f"Error reading PDF: {str(e)}"]

    def search_all_pdfs(self, search_name):
        """Search for name in all downloaded PDFs"""
        print(f"\nSearching for '{search_name}' in all PDFs...")
        
        results = {
            'cap1': [],
            'cap2': []
        }
        
        for cap_round in ['cap1', 'cap2']:
            cap_dir = f"{self.pdf_dir}/{cap_round}"
            if not os.path.exists(cap_dir):
                continue
                
            pdf_files = [f for f in os.listdir(cap_dir) if f.endswith('.pdf')]
            print(f"Searching {len(pdf_files)} {cap_round.upper()} PDFs...")
            
            for pdf_file in pdf_files:
                pdf_path = os.path.join(cap_dir, pdf_file)
                institute_code = pdf_file.split('_')[0]
                
                found, context = self.search_pdf(pdf_path, search_name)
                if found:
                    college_name = self.colleges_data.get(institute_code, {}).get('name', f'Institute {institute_code}')
                    results[cap_round].append({
                        'institute_code': institute_code,
                        'college_name': college_name,
                        'pdf_file': pdf_file,
                        'context': context
                    })
                    print(f"✓ Found in {cap_round.upper()}: {institute_code} - {college_name}")
        
        return results

    def display_results(self, results, search_name):
        """Display search results in a formatted way"""
        print(f"\n{'='*80}")
        print(f"SEARCH RESULTS FOR: {search_name}")
        print(f"{'='*80}")
        
        total_found = len(results['cap1']) + len(results['cap2'])
        if total_found == 0:
            print(f"❌ Name '{search_name}' not found in any PDF.")
            print("Possible reasons:")
            print("- Name not in allotment lists")
            print("- Name spelled differently")
            print("- PDFs for relevant colleges not available")
            return
        
        print(f"✅ Name found in {total_found} PDF(s)\n")
        
        for cap_round in ['cap1', 'cap2']:
            if results[cap_round]:
                print(f"\n{cap_round.upper()} RESULTS:")
                print("-" * 40)
                
                for result in results[cap_round]:
                    print(f"Institute Code: {result['institute_code']}")
                    print(f"College: {result['college_name']}")
                    print(f"PDF File: {result['pdf_file']}")
                    if result['context']:
                        print("Context:")
                        for line in result['context']:
                            print(f"  → {line}")
                    print()

    def run(self):
        """Main execution method"""
        print("DSE CET Allotment Searcher")
        print("=" * 30)
        
        # Step 1: Get college data
        self.scrape_college_data()
        
        # Step 2: Download PDFs
        download_choice = input("\nDownload PDFs? (y/n, default=y): ").strip().lower()
        if download_choice != 'n':
            self.download_all_pdfs()
        
        # Step 3: Search for name
        while True:
            search_name = input("\nEnter name to search (or 'quit' to exit): ").strip()
            if not search_name or search_name.lower() == 'quit':
                break
            
            if len(search_name) < 3:
                print("Please enter at least 3 characters for search.")
                continue
            
            results = self.search_all_pdfs(search_name)
            self.display_results(results, search_name)
            
            # Ask if user wants to search again
            continue_choice = input("\nSearch for another name? (y/n): ").strip().lower()
            if continue_choice == 'n':
                break

def main():
    """Main function"""
    try:
        searcher = DSEAllotmentSearcher()
        searcher.run()
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    # Check dependencies
    try:
        import PyPDF2
        import requests
        from bs4 import BeautifulSoup
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install required packages with:")
        print("pip install PyPDF2 requests beautifulsoup4")
        sys.exit(1)
    
    main()