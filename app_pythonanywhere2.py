from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from flask import Flask, request, jsonify
import os
import time
import subprocess
import sys
import importlib

app = Flask(__name__)

# Auto-install dependencies on startup
def auto_install_requirements():
    """Automatically install required packages if they're missing"""
    requirements = [
        'selenium',
        'flask',
        'selenium-wire',  # Optional, but try to install
    ]
    
    print("🔍 Checking and installing required packages...")
    
    for package in requirements:
        try:
            # Try to import the package
            if package == 'selenium-wire':
                importlib.import_module('seleniumwire')
            else:
                importlib.import_module(package)
            print(f"✅ {package} is already installed")
        except ImportError:
            print(f"📦 Installing {package}...")
            try:
                # Install the package using pip
                subprocess.check_call([
                    sys.executable, 
                    '-m', 
                    'pip', 
                    'install', 
                    package,
                    '--quiet'  # Reduce output noise
                ])
                print(f"✅ Successfully installed {package}")
            except subprocess.CalledProcessError as e:
                print(f"⚠️ Failed to install {package}: {e}")
                # Continue even if one package fails

def install_from_requirements_txt():
    """Alternative method: install from requirements.txt if it exists"""
    if os.path.exists('requirements.txt'):
        print("📦 Found requirements.txt, installing dependencies...")
        try:
            subprocess.check_call([
                sys.executable, 
                '-m', 
                'pip', 
                'install', 
                '-r', 
                'requirements.txt',
                '--quiet'
            ])
            print("✅ Requirements installed successfully!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Failed to install requirements.txt: {e}")
            return False
    return False

# Run auto-installation
print("=" * 60)
print("🚀 Starting Selenium Flask Server...")
print("=" * 60)

# First try requirements.txt
if not install_from_requirements_txt():
    # Fallback to manual installation
    auto_install_requirements()

# Now import selenium-wire only if needed (after potential installation)
try:
    from seleniumwire import webdriver as wire_driver
    SELENIUM_WIRE_AVAILABLE = True
except ImportError:
    SELENIUM_WIRE_AVAILABLE = False
    print("⚠️ selenium-wire not available, will use standard driver")

# Initialize Chrome options
chrome_options = Options()
chrome_options.add_argument('--headless')  # Headless mode
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument('--disable-gpu')
chrome_options.add_argument('--window-size=1920,1080')

# Set Chrome binary location
chrome_options.binary_location = '/usr/bin/chromium'

# Add experimental options for headers (works with Chrome 90+)
chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
chrome_options.add_experimental_option('useAutomationExtension', False)

# Initialize driver with custom capabilities
def create_driver():
    """Create driver with proper header injection setup"""
    try:
        driver = webdriver.Chrome(options=chrome_options)
        
        # Enable Network domain for CDP commands
        driver.execute_cdp_cmd('Network.enable', {})
        
        # Set headers using CDP - this works for ALL requests
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
            'headers': {
                'ngrok-skip-browser-warning': '1',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 MyApp/1.0'
            }
        })
        
        print("✅ Browser initialized with ngrok skip headers!")
        return driver
    except Exception as e:
        print(f"❌ Error initializing browser: {e}")
        return None

# Method 2: Using Selenium Wire for better header control (Alternative)
def create_driver_with_wire():
    """Create driver using selenium-wire for more reliable headers"""
    if not SELENIUM_WIRE_AVAILABLE:
        return None
        
    try:
        options = {
            'disable_encoding': True,
            'request_storage': 'memory',
            'request_storage_max_size': 100,
            'ignore_ssl_errors': True,
        }
        
        driver = wire_driver.Chrome(
            options=chrome_options,
            seleniumwire_options=options
        )
        
        # Interceptor to add headers to every request
        def interceptor(request):
            request.headers['ngrok-skip-browser-warning'] = '1'
            request.headers['User-Agent'] = 'Mozilla/5.0 (compatible; MyApp/1.0)'
        
        driver.request_interceptor = interceptor
        
        print("✅ Browser initialized with selenium-wire headers!")
        return driver
    except ImportError:
        print("⚠️ selenium-wire not installed, using standard driver")
        return None
    except Exception as e:
        print(f"❌ Error with selenium-wire: {e}")
        return None

# Try to create driver with preferred method
driver = create_driver()
if driver is None and SELENIUM_WIRE_AVAILABLE:
    # Fallback to selenium-wire if available
    driver = create_driver_with_wire()

@app.route('/')
def index():
    return jsonify({
        'status': 'running',
        'browser_initialized': driver is not None,
        'message': 'Persistent Selenium Flask Server - Ngrok skip header enabled',
        'headers': {
            'ngrok-skip-browser-warning': '1',
            'user_agent': 'MyApp/1.0'
        },
        'solution': 'Headers are automatically injected to skip ngrok interstitial'
    })

@app.route('/fetch', methods=['GET', 'POST'])
def fetch():
    if driver is None:
        return jsonify({'error': 'Browser not initialized'}), 500
    
    url = request.args.get('url') or request.json.get('url')
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    try:
        # Method 1: Re-inject headers before navigation
        try:
            driver.execute_cdp_cmd('Network.enable', {})
            driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
                'headers': {
                    'ngrok-skip-browser-warning': '1',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 MyApp/1.0'
                }
            })
        except:
            pass  # Ignore if CDP fails
        
        # Navigate to URL
        driver.get(url)
        
        # Wait a moment for page to load
        time.sleep(1)
        
        # Method 2: If still on interstitial, try to click through
        current_url = driver.current_url
        page_source = driver.page_source
        
        # Check if we're on ngrok interstitial
        if 'ngrok-free.app' in current_url and 'ERR_NGROK' in page_source:
            print("⚠️ Interstitial detected, trying to click through...")
            
            try:
                # Try to find and click the "Visit" button
                visit_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Visit')]"))
                )
                visit_button.click()
                time.sleep(2)
                
                # Get the actual page content after clicking
                page_source = driver.page_source
                current_url = driver.current_url
                print("✅ Clicked through interstitial!")
            except Exception as e:
                print(f"⚠️ Could not click through automatically: {e}")
                # Try alternative: click on the link
                try:
                    continue_link = driver.find_element(By.CSS_SELECTOR, 'a[href*="continue"]')
                    continue_link.click()
                    time.sleep(2)
                    page_source = driver.page_source
                    current_url = driver.current_url
                except:
                    pass
        
        # Get page info
        title = driver.title
        
        return jsonify({
            'url': current_url,
            'title': title,
            'content_length': len(page_source),
            'content': page_source[:1000],  # Truncate for response
            'status': 'success',
            'ngrok_skip_used': True,
            'interstitial_bypassed': 'ERR_NGROK' not in page_source
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Method 3: Special endpoint that handles ngrok URLs specifically
@app.route('/fetch_ngrok', methods=['POST'])
def fetch_ngrok():
    """Specialized endpoint for fetching ngrok URLs with proper bypass"""
    if driver is None:
        return jsonify({'error': 'Browser not initialized'}), 500
    
    data = request.json
    target_url = data.get('url')
    
    if not target_url:
        return jsonify({'error': 'URL parameter required'}), 400
    
    try:
        # First set up headers
        driver.execute_cdp_cmd('Network.enable', {})
        driver.execute_cdp_cmd('Network.setExtraHTTPHeaders', {
            'headers': {
                'ngrok-skip-browser-warning': '1',
                'User-Agent': 'Mozilla/5.0 (compatible; MyApp/1.0)'
            }
        })
        
        # Go to the URL
        driver.get(target_url)
        time.sleep(2)
        
        # Handle interstitial if present
        page_source = driver.page_source
        
        # If we hit the interstitial, click through
        if 'ERR_NGROK_6024' in page_source:
            print("🔄 Interstitial detected, clicking through...")
            
            # Try multiple ways to bypass
            bypass_methods = [
                # Method A: Click "Visit" button
                lambda: driver.find_element(By.XPATH, "//button[contains(text(), 'Visit')]").click(),
                # Method B: Click continue link
                lambda: driver.find_element(By.CSS_SELECTOR, 'a[href*="continue"]').click(),
                # Method C: Click any button or link with "continue" or "visit"
                lambda: driver.find_element(By.XPATH, "//*[contains(text(), 'Continue') or contains(text(), 'Visit')]").click()
            ]
            
            for method in bypass_methods:
                try:
                    method()
                    time.sleep(2)
                    print("✅ Bypassed successfully!")
                    break
                except:
                    continue
            
            # Get final page source
            page_source = driver.page_source
            current_url = driver.current_url
        
        return jsonify({
            'url': driver.current_url,
            'title': driver.title,
            'content_length': len(page_source),
            'content': page_source[:2000],  # Slightly longer for testing
            'bypassed': 'ERR_NGROK' not in page_source
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/install_package', methods=['POST'])
def install_package():
    """Endpoint to install additional Python packages on the fly"""
    data = request.json
    package = data.get('package')
    
    if not package:
        return jsonify({'error': 'Package name required'}), 400
    
    try:
        print(f"📦 Installing package: {package}")
        result = subprocess.run([
            sys.executable,
            '-m',
            'pip',
            'install',
            package,
            '--quiet'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'package': package,
                'message': f'Successfully installed {package}',
                'output': result.stdout
            })
        else:
            return jsonify({
                'success': False,
                'package': package,
                'error': result.stderr
            }), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/install_requirements', methods=['POST'])
def install_requirements():
    """Endpoint to install packages from a requirements.txt file"""
    # Check if requirements.txt exists
    if not os.path.exists('requirements.txt'):
        return jsonify({'error': 'requirements.txt not found'}), 404
    
    try:
        print("📦 Installing from requirements.txt...")
        result = subprocess.run([
            sys.executable,
            '-m',
            'pip',
            'install',
            '-r',
            'requirements.txt',
            '--quiet'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            return jsonify({
                'success': True,
                'message': 'Successfully installed all requirements',
                'output': result.stdout
            })
        else:
            return jsonify({
                'success': False,
                'error': result.stderr
            }), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🌐 Persistent Selenium Flask Server")
    print(f"Headless mode: True")
    print(f"Persistent session: True (browser stays open)")
    print(f"Ngrok skip header: Enabled (automatically bypasses interstitial)")
    print("Server running at: http://127.0.0.1:5000")
    print("\nTo use with ngrok:")
    print("  1. Run: ngrok http 5000")
    print("  2. Access your app via the ngrok URL")
    print("  3. All requests will automatically skip the interstitial")
    print("\nTest endpoints:")
    print("  POST /fetch_ngrok - For ngrok URLs specifically")
    print("  POST /fetch - For any URL")
    print("  POST /install_package - Install additional packages on the fly")
    print("  POST /install_requirements - Install from requirements.txt")
    print("=" * 60)
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        if driver:
            driver.quit()
            print("🔄 Browser closed.")