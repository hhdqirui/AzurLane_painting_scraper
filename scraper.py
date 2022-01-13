from selenium.webdriver import Chrome
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver import ActionChains
import time, requests, os, string, re

URL = 'https://azurlane.koumakan.jp/wiki/List_of_Ships_by_Type'
DRIVER_PATH = 'chromedriver.exe'

def get_imgs_of_interest(browser, ship_name):
    img_element = browser.find_elements_by_class_name('image')
    imgs_of_interest = []
    for im in img_element:
        try:
            # if a space is present in the ship name, create another name by replacing the space with "_"
            # as some ship name contains "_" instead of a space, e.g. Giulio_Cesare instead of Giulio Cesare
            ship_name2 = re.sub('\s+', '_' , ship_name)
            im_href = im.get_attribute('href')
            # the following is to take only the default skin in each skin tab
            is_ship_name_in_href = ship_name in im_href
            is_ship_name2_in_href = ship_name2 in im_href
            is_Chibi_in_href = 'Chibi' in im_href
            is_WithoutBG_in_href = 'WithoutBG' in im_href
            is_Censored_in_href = 'Censored' in im_href
            is_CN_in_href = 'CN.png' in im_href
            is_WithoutRigging_in_href = 'WithoutRigging.png' in im_href
            is_EN_in_href = 'EN.png' in im_href
            is_TW_in_href = 'TW.png' in im_href
            is_png_in_href = '.png' in im_href
            if (not is_ship_name_in_href and not is_ship_name2_in_href) or is_Chibi_in_href or is_WithoutBG_in_href or is_Censored_in_href or is_CN_in_href or is_WithoutRigging_in_href or is_EN_in_href or is_TW_in_href or not is_png_in_href:
                print('passing {} {} {} {} {} {} {} {} {} {} {}'.format(im_href, is_ship_name_in_href, is_ship_name2_in_href, is_Chibi_in_href, is_WithoutBG_in_href, is_Censored_in_href, is_CN_in_href, is_WithoutRigging_in_href, is_EN_in_href, is_TW_in_href, is_png_in_href))
                continue
            print(im_href)
            img = im.find_element_by_tag_name('img')
            imgs_of_interest.append(img)
        except:
            pass
    return imgs_of_interest

def get_skin_tabs(browser):
    img_ul = browser.find_element_by_class_name('tabbernav')
    skin_tabs = img_ul.find_elements_by_tag_name('li')
    return skin_tabs

browser = Chrome(executable_path=DRIVER_PATH)
browser.get(URL)
# the x and y coordinate of the mouse cursor to click the "More details" button in the media viewer
x = 913
y = 654
# counter variable of all ships
cnt = 538
moved = False

save_file_path = os.path.join(os.getcwd(), 'images')
is_save_file_path_existed = os.path.exists(save_file_path)
if not is_save_file_path_existed:
    os.mkdir(save_file_path)
os.chdir(save_file_path)

time.sleep(2)
all_ships_alicon = browser.find_elements_by_class_name('alicon')

print('Total: {} ships'.format(len(all_ships_alicon)))

while(cnt < len(all_ships_alicon)):
    alicon = all_ships_alicon[cnt]
    cnt += 1
    alicon.click()
    time.sleep(1)
    ship_name = browser.find_element_by_id('firstHeading').text
    print('Now scraping {}'.format(ship_name))

    gallery = browser.find_element_by_xpath("//*[contains(text(), 'Gallery')]")
    gallery.click()
    time.sleep(1)

    img_ul = browser.find_element_by_class_name('tabbernav')
    skin_tabs = img_ul.find_elements_by_tag_name('li')
    skin_names = []
    for t in skin_tabs:
        skin_names.append(t.find_element_by_tag_name('a').get_attribute('title'))
    print(skin_names)
    imgs_of_interest = get_imgs_of_interest(browser, ship_name)
    print(len(imgs_of_interest))

    skin_cnt = 0
    skin_tab = skin_tabs[0]
    skin_tab.click()
    while skin_cnt < len(imgs_of_interest):
        im = imgs_of_interest[skin_cnt]
        skin_name = skin_names[skin_cnt]
        skin_name = skin_name.translate(str.maketrans('', '', string.punctuation))
        skin_cnt += 1
        alt = str(im.get_attribute('alt'))
        if '.png' not in alt or 'WithoutBG' in alt or 'Censored' in alt:
            continue
        im.click()
        time.sleep(2)
        # we use mouse clicking here as I cannot get the "More details" button element
        click_more_details = ActionChains(browser)
        if not moved:
            click_more_details.move_by_offset(x, y).perform()
            moved = True
        click_more_details.click().perform()
        original_file = browser.find_element_by_xpath("//*[contains(text(), 'Original file')]")
        original_file.click()
        img_src = browser.find_element_by_tag_name('img').get_attribute('src')
        res = requests.get(img_src)
        file_name = '{}_{}.png'.format(ship_name, skin_name)
        if res.status_code == 200:
            with open(f"{ship_name}_{skin_name}.png", 'wb') as file:
                print('Writing {}'.format(file_name))
                file.write(res.content)
        else:
            print('{}_{}.png status code not 200'.format(ship_name, skin_name))
        browser.back()
        time.sleep(1)
        browser.back()
        time.sleep(1)
        browser.back()
        time.sleep(1)
        skin_tabs = get_skin_tabs(browser)
        if skin_cnt >= len(skin_tabs):
            break
        skin_tab = skin_tabs[skin_cnt]
        skin_tab.click()
        time.sleep(1)
        imgs_of_interest = get_imgs_of_interest(browser, ship_name)
        
    browser.get(URL)
    all_ships_alicon = browser.find_elements_by_class_name('alicon')
    print('Now have {} ships, cnt: {}'.format(len(all_ships_alicon), cnt))

print('cnt: {}'.format(cnt))
