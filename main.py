# Local modules
import signal, gi, os, json, webbrowser, time, subprocess, configparser

# Gtk & Threading
gi.require_version('Gtk', '3.0')
gi.require_version('AppIndicator3', '0.1')
from gi.repository import Gtk, AppIndicator3, GObject, Pango
from threading import Thread

# Local helper module
import helpers



# Preprocessing from config.ini before gtk is initialized
config = configparser.ConfigParser()
config.readfp(open(r'config.ini'))

# Read initial coins
coins = json.loads(config.get('INDICATOR_OPTIONS', 'COINS_TO_SHOW'))


# Read booleans that will be used to create indicator label & menus later on
display_holdings = (config.get('INDICATOR_OPTIONS', 'DISPLAY_HOLDINGS_IN_MENU') == '1')
display_holdings_label = (config.get('INDICATOR_LABELS', 'DISPLAY_TOTAL_HOLDINGS_IN_INDICATOR_LABEL') == '1')


# Copy of coins to show from attribute which gets appended with holdings to create url req to cryptocompare
primary_coins = json.loads(config.get('INDICATOR_OPTIONS', 'COINS_TO_SHOW'))


# Structures to track coin lists
base_coins = []
base_coins.append(config.get('INDICATOR_OPTIONS', 'COINS_BASE_VALUE'))

holding_coins = []
holding_vals = []

silent_holding_coins = []
silent_holding_vals = []

# Initialize list with data from config.ini, these will be used to create API request
# Base coins will be used as 'to' coin query param
for main_pair in json.loads(config.get('INDICATOR_LABELS', 'PAIRS')):
    primary_coins.append(main_pair[0].upper())
    base_coins.append(main_pair[1].upper())

# Primary coins will be used as 'from' coin query param
for holdings_pair in config.items('HOLDINGS'):
    primary_coins.append(holdings_pair[0].upper())
    holding_coins.append(holdings_pair[0].upper())
    holding_vals.append(holdings_pair[1])

# Show everything on this list. Check before displaying the ones on silent holdings
coins_to_show = list(primary_coins)

for silent_holdings_pair in config.items('SILENT_HOLDINGS'):
    primary_coins.append(silent_holdings_pair[0].upper())
    silent_holding_coins.append(silent_holdings_pair[0].upper())
    silent_holding_vals.append(silent_holdings_pair[1])


# Lists -> Set -> List while preserving order // Out final data stores
primary_coins = helpers.list_to_set_preserve_order(primary_coins)
base_coins = helpers.list_to_set_preserve_order(base_coins)
coins_to_show = helpers.list_to_set_preserve_order(coins_to_show)
base_value = config.get('INDICATOR_OPTIONS', 'COINS_BASE_VALUE').replace("\"","").replace("'","")
display_indicator = [['ETH', 'USD'], ['ETH','BTC']]

# Construct url to send request to
url = "https://min-api.cryptocompare.com/data/pricemultifull?fsyms=" + ",".join(primary_coins) + "&tsyms=" +  ",".join(base_coins) + "," + base_value

# Send HTTP request to cryptocompare API for first time for initialization
prices = helpers.get_prices(url)

# Grab main 'symbol'
# TODO: Add base conversions according to main_symbol instead of binding it to usd 
main_symbol = str(prices['DISPLAY'][str((list(prices['DISPLAY'].keys())[0]))][base_value]['PRICE'])
main_symbol = ''.join(i for i in main_symbol if not i.isdigit()).replace(".","").replace(",","").strip()

# Get separator from config.ini, some people might have different ideas
separator = " " + (config.get('INDICATOR_LABELS', 'SEPARATOR_SYMBOL')).replace("\"","").replace("'","")+ " "
# This will hold main crypto-indicator label
initial_display_string = ''

# Construct Label
each_label = []
for label in json.loads(config.get('INDICATOR_LABELS', 'PAIRS')):
    each_label.append(helpers.get_init_price(prices,label[0],label[1]))
initial_display_string =  separator.join(each_label) 

# Begin Main Indicator Class
class Indicator():
    def __init__(self):
        self.app = 'crypto-indicator'
        iconpath = os.path.abspath("indicator-icon.svg")
        self.indicator = AppIndicator3.Indicator.new(self.app, iconpath, AppIndicator3.IndicatorCategory.OTHER)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.sub_menus = self.create_menu()
        self.indicator.set_menu(self.sub_menus)
        # Update on a new thread
        self.update = Thread(target=self.update_indicator)
        # Run thread as daemon so indicator can be stopped
        self.update.setDaemon(True)
        self.update.start()

    # Action Event for 'About' Option
    def open_about(self, *args):
        webbrowser.open('https://www.github.com/ankitgyawali/crypto-indicator', new=2)    

    # Action Event for 'Configure' Option
    # TODO: xdg-open config.ini does not work for some reason, so we display users a link to config.ini instead
    def configure_window(self, *args):
        subprocess.call(["xdg-open", os.path.abspath("config.ini")]) # Doesn't work for some reason, threading issues?
        # Construct window
        window = Gtk.Window()
        window.set_border_width(20)
        vert = Gtk.Orientation.VERTICAL
        horz = Gtk.Orientation.HORIZONTAL
        main_box = Gtk.Box(orientation=vert, spacing=5)
        listbox = Gtk.ListBoxRow()
        main_box.pack_start(listbox, True, True, 0)
        label = Gtk.Label()
        label.set_markup("Configure your coins on the following ini file with your favourite text editor. \n ~/.config/crypto-indicator-config.ini \n \n Instructions provided on the .ini file.\n More detailed instructions provided on <a href='https://www.github.com/ankitgyawali'>https://www.github.com/ankitgyawali</a>")
        label.set_selectable(True)
        main_box.add(label)
        window.set_position(Gtk.WindowPosition.CENTER)
        window.add(main_box)
        window.show_all()
        # Focus window when clicked
        gtk.Window.present()

    def stop(self, source):
        Gtk.main_quit()

    # Following function initialize first menu rows
    def create_menu(self):
        self.menu = Gtk.Menu()
        # Create Menu header
        self.menu.append(Gtk.MenuItem(helpers.create_a_header("Coin",  "     24hr +/- %", "   Price ("+base_value+")", display_holdings)))
        self.menu.append(Gtk.SeparatorMenuItem())

        # Get data used to populate menu rows for each coins using preprocessed data from earlier
        # make_menu function call will populate current object with menu rows in addition to all the processing for update even later on
        holdings_val, old_holdings_val = make_menus(prices,display_holdings, coins_to_show, holding_coins, holding_vals,silent_holding_coins, silent_holding_vals, self.menu, self)
        
        # Calculate % difference 24 hours for total holdings & prettify before displaying
        diff = helpers.process_coin_change((sum(holdings_val) - sum(old_holdings_val)) / sum(old_holdings_val))
        holdings = " $" + ("%.2f" % (sum(holdings_val)))
        self.total_holdings_item = Gtk.MenuItem.new_with_label("Total Holdings: " + holdings + " ("+ diff + ")")

        ## Update label 
        holdings_label = ''
        if(display_holdings_label):
            holdings_label = " " + separator + "Holdings: " + holdings

        # Main indicator label Set here
        self.indicator.set_label(initial_display_string + holdings_label, self.app)
        self.menu.append(Gtk.SeparatorMenuItem())

        # After all the coins have been appended from make_menu function display total holdings
        self.menu.append(self.total_holdings_item)
        self.menu.append(Gtk.SeparatorMenuItem())          

        # Add configure menu option & callback to function defined earlier
        about = Gtk.MenuItem('Configure')
        self.menu.append(about)
        about.connect('activate', self.configure_window)
        
        # Add About menu option & callback to function defined earlier        
        config_indicator = Gtk.MenuItem('About')
        self.menu.append(config_indicator)
        config_indicator.connect("activate", self.open_about)        

        # Add Quit menu option & callback to function defined earlier        
        item_quit = Gtk.MenuItem('Quit')
        item_quit.connect('activate', self.stop)
        self.menu.append(item_quit)

        # Show everything return menu to class construcor
        self.menu.show_all()
        return self.menu

    # Update in a new thread
    def update_indicator(self):
        while True:
            # Sleep configured second, minimum 15 seconds interval to avoid rate limit issues
            time_to_sleep = 15 if (int(config.get('INDICATOR_OPTIONS', 'REFRESH_TIME_IN_SECONDS')) < 15) else int(config.get('INDICATOR_OPTIONS', 'REFRESH_TIME_IN_SECONDS'))
            time.sleep(time_to_sleep)

            # Update indicator label, we've done thise before, could technically be abstracted out to a single function
            separator = " " + (config.get('INDICATOR_LABELS', 'SEPARATOR_SYMBOL')).replace("\"","").replace("'","")+ " "
            initial_display_string = ''
            each_label = []

            # HTTP call to cyrptocompare API
            prices = helpers.get_prices(url)            
            
            for label in json.loads(config.get('INDICATOR_LABELS', 'PAIRS')):
                each_label.append(helpers.get_init_price(prices,label[0],label[1]))
            initial_display_string =  separator.join(each_label)

            # Create & update each menu row label string
            all_holdings = []
            old_holdings_val = []
            for silent_coin in silent_holding_coins:
                all_holdings.append(helpers.calculate_coin_holding(prices['RAW'][silent_coin][base_value]['PRICE'], silent_holding_vals[silent_holding_coins.index(silent_coin)].replace(",","")))

            # We are looping through self.coin_name/self.coin_menu_rows constructed at make_menus defined below during initialization, which contain all menu row objects
            for idx, coin in enumerate(self.coin_names):
                coin_symbol = str(prices['RAW'][coin][base_value]['FROMSYMBOL'])
                coin_price = prices['DISPLAY'][coin][base_value]['PRICE']
                coin_change = helpers.process_coin_change((prices['RAW'][coin][base_value]['PRICE'] - prices['RAW'][coin][base_value]['OPEN24HOUR'])/prices['RAW'][coin][base_value]['PRICE'])
                coin_change+= ' ' * (21 - len(coin_change))
                menu_string = helpers.column_normalizer(coin_symbol) + helpers.column_normalizer(coin_change) + helpers.column_normalizer(coin_price)
                if (display_holdings and (coin in holding_coins)): # This condition checks for holdings that are also shown
                    all_holdings.append(helpers.calculate_coin_holding(prices['RAW'][coin][base_value]['PRICE'], holding_vals[holding_coins.index(coin)].replace(",","")))
                    old_holdings_val.append(helpers.calculate_coin_holding(prices['RAW'][coin][base_value]['OPEN24HOUR'], holding_vals[holding_coins.index(coin)].replace(",","")))
                    menu_string += "$" + ("%.4f" % helpers.calculate_coin_holding(prices['RAW'][coin][base_value]['PRICE'], holding_vals[holding_coins.index(coin)].replace(",","")))
                # Finally update menu label for each coin
                GObject.idle_add(self.coin_menu_rows[idx].set_label, str(menu_string))
            # Update total holdings menu row
            holdings = " $" + ("%.2f" % (sum(all_holdings)))
            diff = helpers.process_coin_change((sum(all_holdings) - sum(old_holdings_val)) / sum(old_holdings_val))            
            GObject.idle_add(self.total_holdings_item.set_label, "Total Holdings: " + holdings + " ("+ diff + ")")

            # Update indicator label with new data
            holdings_label = ''
            if(display_holdings_label):
                holdings_label = " " + separator + "Holdings: " + holdings

            GObject.idle_add(self.indicator.set_label, initial_display_string + holdings_label, self.app, priority=GObject.PRIORITY_DEFAULT)

# Initialize menu rows during Indicator constructions. Gets bunch of preprocessed data from initial HTTP call
# Stores each rows inside object property so it can be updated easily later on
def make_menus(prices, display_holdings, coins_to_show, holding_coins, holding_vals, silent_holding_coins, silent_holding_vals, menu, self):
    self.coin_menu_rows = []
    self.coin_names = []
    all_holdings = []
    old_holdings_value = []
    # Calculate silent holding prices & add it to all_holdings list without display the coin as menu
    for silent_coin in silent_holding_coins:
        all_holdings.append(helpers.calculate_coin_holding(prices['RAW'][silent_coin][base_value]['PRICE'], silent_holding_vals[silent_holding_coins.index(silent_coin)].replace(",","")))
    # Create labels & show menu row for each coins
    for coin in coins_to_show:
        coin_symbol = str(prices['RAW'][coin][base_value]['FROMSYMBOL'])
        coin_price = prices['DISPLAY'][coin][base_value]['PRICE']
        coin_change = helpers.process_coin_change((prices['RAW'][coin][base_value]['PRICE'] - prices['RAW'][coin][base_value]['OPEN24HOUR'])/prices['RAW'][coin][base_value]['PRICE'])
        coin_change+= ' ' * (21 - len(coin_change))
        menu_string = helpers.column_normalizer(coin_symbol) + helpers.column_normalizer(coin_change) + helpers.column_normalizer(coin_price)
        if (display_holdings and (coin in holding_coins)): # This condition checks for holdings that are also shown
            all_holdings.append(helpers.calculate_coin_holding(prices['RAW'][coin][base_value]['PRICE'], holding_vals[holding_coins.index(coin)].replace(",","")))
            old_holdings_value.append(helpers.calculate_coin_holding(prices['RAW'][coin][base_value]['OPEN24HOUR'], holding_vals[holding_coins.index(coin)].replace(",","")))
            menu_string += "$" + ("%.4f" % helpers.calculate_coin_holding(prices['RAW'][coin][base_value]['PRICE'], holding_vals[holding_coins.index(coin)].replace(",","")))
        self.coin_names.append(coin)
        # Append coin id's & GTK.ImageMenuItem object so it can be updated easily later on
        self.coin_menu_rows.append(Gtk.ImageMenuItem.new_with_label(menu_string))
        self.coin_menu_rows[-1].set_always_show_image(True)
        self.coin_menu_rows[-1].set_image(Gtk.Image.new_from_file(os.path.abspath("icons/"+ coin_symbol +".png")))
        menu.append(self.coin_menu_rows[-1])
    # Return total holdings value now & holdings value 24 hrs earlier to display % change
    return all_holdings, old_holdings_value

# Initialize Indicator class
Indicator()
# this is where we call GObject.threads_init()
GObject.threads_init()
signal.signal(signal.SIGINT, signal.SIG_DFL)
Gtk.main()