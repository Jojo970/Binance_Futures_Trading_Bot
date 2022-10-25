import talib, time, json, requests
from decimal import Decimal
from datetime import datetime
import numpy as np
from binance.client import Client
from binance.websockets import BinanceSocketManager
import twitter

twitterapi = twitter.Api(consumer_key='INSERT CONSUMER KEY', #Need own access tokens for twitter posts.
                consumer_secret='INSERT CONSUMER SECRET KEY',
                access_token_key='INSERT ACCESS TOKEN KEY',
                access_token_secret='INSERT ACCESS SECRET KEY')

binance_coin = 'LTCUSDT' #INSERT WHICH PAIR TO TRADE HERE

api_key_in = '' #Need your own here
api_secret_in = '' #Need your own here



class Process: # TO READ MESSAGES FROM THE LIVE DATA SOCKET
    
    def process_message(self, msg):
        # print("message type: {}".format(msg['e']))
        self.msg = msg
        if self.msg['k']['x'] == True:
            self.lasthighs.append(float(self.msg['k']['h']))
            self.lastlows.append(float(self.msg['k']['l']))
            self.lastcloses.append(float(self.msg['k']['c']))
    
    def process_mark(self, markmsg):
        self.mark = markmsg
        self.markprice = float(self.mark['data']['p'])

        self.lst_of_price[0] = self.markprice

class GetBinanceClient(Process):

    def __init__(self, api_key, api_secret): # IGNORE THIS, MAKING INITIAL LISTS
        self.lsthighs = []
        self.lstlows = []
        self.lstcloses = []
        self.lst_of_price = [0]

        self.api_key = api_key
        self.api_secret = api_secret

    def b_getclient(self): # CREATES WEBSOCKET
        self.client = Client(self.api_key, self.api_secret)
        self.bm = BinanceSocketManager(self.client)

    def b_getdata(self): # STARTS DATAFEED
        self.bm.start_kline_socket(binance_coin, super().process_message, interval = Client.KLINE_INTERVAL_4HOUR)
        self.bm.start_symbol_mark_price_socket(binance_coin, super().process_mark, fast = False)
        self.bm.start()   

    def b_get_market_price(self):
        self.market_price = self.lst_of_price[0]
        return self.market_price

    def b_get_funding_rate(self):
        self.funding_lib = self.client.futures_funding_rate(symbol = binance_coin, limit = 1)
        self.funding_rate = float(self.funding_lib[0]['fundingRate']) * 100
        return self.funding_rate

    def b_getpastdata(self): # GETS PAST KLINES TO USE FOR INITIAL DATA
        self.candles = self.client.futures_klines(symbol=binance_coin, interval = Client.KLINE_INTERVAL_4HOUR)
        for data in self.candles:
            highs = float(data[2])
            lows = float(data[3])
            closes = float(data[4])

            self.lsthighs.append(highs)
            self.lstlows.append(lows)
            self.lstcloses.append(closes)
        
        self.lsthighs.pop(-1)
        self.lstlows.pop(-1)
        self.lstcloses.pop(-1)

        self.lastcloses = self.lstcloses[-50:]
        self.lasthighs = self.lsthighs[-50:]
        self.lastlows = self.lstlows[-50:]
        
        del self.lstcloses
        del self.lsthighs
        del self.lstlows

    def b_get_rsi_stoch(self): #For updating RSI/STOCH based on incoming data
        self.lastcloses = self.lastcloses

        self.np_closes = np.array(self.lastcloses[-50:])
        self.np_highs = np.array(self.lasthighs[-50:])
        self.np_lows = np.array(self.lastlows[-50:])

        self.b_slowk, self.b_slowd = talib.STOCH(self.np_highs, self.np_lows, self.np_closes, 8, 3, 0, 3, 0)
        self.b_rsi = talib.RSI(self.np_closes, 14)
        self.b_realslowk = round(self.b_slowk[-1], 2)
        self.b_realrsi = round(self.b_rsi[-1], 2)

        return self.b_realslowk, self.b_realrsi

    def b_trade_signal(self, coin, price, side):
        self.client = Client(self.api_key, self.api_secret) # IF NOT IN ORDER THIS PROTOCAL IS ACTIVATED
        self.USDT_balance = self.client.futures_account_balance() # CHECK BALANCE
        self.funds = float(self.USDT_balance[0]['balance'])
        self.funds_to_trade = self.funds * 0.05 # mulitply self.funds by percent of funds to use
        self.stop_price = round(price + 0.5, 2)
        self.quantity = (self.funds_to_trade / price) # how many orders to send in
        self.trade_quantity = round(self.quantity, 3)
        self.client.futures_create_order(symbol = coin, side = 'BUY', position_side = side, 
        type = 'STOP_MARKET', quantity = self.quantity, stopPrice = self.stop_price)

    def b__sell_signal(self, coin, side):
        self.client.futures_create_order(symbol = coin, side = 'SELL', position_side = side, 
        type = 'STOP_MARKET', closePosition = True)



binance = GetBinanceClient(api_key_in,
 api_secret_in)

sidelng = False
sideshrt = False
orderplaced = False
threshold = False
fund_check = False

candle_rsi = 0
count = 5

max_tries = 0

binance.b_getclient()
binance.b_getpastdata()
binance.b_getdata()




print("CONNECTION SUCCESSFUL")
time.sleep(5)
while max_tries < 5:
    markprice = binance.b_get_market_price()

    stochk, rsi = binance.b_get_rsi_stoch()

    price = float(markprice)


    if sidelng == False and sideshrt == False and orderplaced == False and count >= 5:


        #The "0"s indicate strategy. Real indicator numbers have been taken out
        if stochk > 0 and rsi < 0 and fund_check == False:
            funding_rate = binance.b_get_funding_rate()
            if funding_rate < 0.001:
                sideshrt = True
                orderplaced = True
                candle_rsi = float(rsi)
                count = 0

                shrt_entry = price

                shrtcall = price + (price * 0.03)
                shrt_threshold = price - (price * 0.0375)
                binance.b_trade_signal(binance_coin, price, "SHORT")
                
                
                print('SHORT POSITION OPENED')
                print('FundRate: ',funding_rate, '\nStock and RSI: ', stochk, rsi)
            else:
                print("Funding rate too high! You wanna lose money?")
                time.sleep(14400)
                fund_check = True
                pass
            
        

                #The "0"s indicate strategy. Real indicator numbers have been taken out
        elif stochk <0 and rsi > 0 and fund_check == False:
            funding_rate = binance.b_get_funding_rate()
            if funding_rate >= 0.001:
                sidelng = True
                orderplaced = True
                candle_rsi = float(rsi)
                count = 0

                lng_entry = price

                lngcall = price - (price * 0.03)
                lng_threshold = price + (price * 0.0375)
                binance.b_trade_signal(binance_coin, price, "LONG")
                

                print('LONG POSITION OPENED')
                print('FundRate: ',funding_rate, '\nStock and RSI: ', stochk, rsi)
            else:
                print("Bro the funding rate says you'll lose money, dont be stupid foo")
                fund_check = True
                time.sleep(14400)
                pass
            
    
    elif orderplaced == True:

        if sidelng == True:

            if price >= lng_threshold:
                threshold = True   
            
            if price <= lngcall: # close the long position
                binance.b__sell_signal(binance_coin, "LONG")

                print('LONG POSITION CLOSED')

                sidelng = False
                orderplaced = False
                threshold = False

                # RECORD DATA TO SEND TO TWITTER
                now = datetime.now(utc)
                selltime = now.strftime("%d/%m/%Y %H:%M:%S")
                lngpnl = str(round((((markprice - lng_entry) / lng_entry) * 100), 2))
                
                #MAKE TWITTER POST
                lngpost = 'LONG TRADE EXECUTED AT: ' + str(round(lng_entry, 2)) + '\n' + "UTC TIME: " + buytime + '\n' + '\n' + 'POSITION CLOSED AT: ' + str(round(markprice, 2)) + '\n' + 'UTC TIME:' + selltime + '\n' + 'PNL %:' + lngpnl + '\n' + '$LTC $BTC #cryptocurrency'
                twitterapi.PostUpdate(lngpost)

            elif threshold == True: #Trailing stop loss calculated here.
                if price > lng_entry:
                    lngcall = price - (price * 0.03)
                    lng_entry = price




        elif sideshrt == True:

            if shrt_threshold >= price:
                threshold = True    

            if price >= shrtcall: # close the short position
                binance.b__sell_signal(binance_coin, "SHORT")
                print('SHORT POSITION CLOSED')
                sideshrt = False
                orderplaced = False
                threshold = False

                #RECORD DATA FOR TWITTER POST
                now = datetime.now(utc)
                selltime = now.strftime("%d/%m/%Y %H:%M:%S")
                shrtpnl = str(round((((markprice - shrt_entry) / shrt_entry) * -100), 2))
                
                #MAKE TWITTER POST
                shortpost = 'SHORT TRADE EXECUTED AT: '+ str(round(shrt_entry, 2)) + '\n' + "UTC TIME: " + buytime + '\n' + '\n' + 'POSITION CLOSED AT: ' + str(round(markprice, 2)) + '\n' + 'UTC TIME: ' + selltime + '\n' + 'PNL %: ' + shrtpnl + '\n' + '$LTC $BTC #cryptocurrency'
                twitterapi.PostUpdate(shortpost)

            elif threshold == True: #Trailing stop loss calculated here.
                if price < shrt_threshold:
                    shrtcall = price + (price* 0.03)
                    shrt_entry = price

            else: pass

                
    if candle_rsi == rsi:
        pass
    elif candle_rsi != rsi:
        count += 1
        candle_rsi = rsi
        fund_check = False
    

    time.sleep(60)
