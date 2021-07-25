#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Jul 11 15:25:16 2021

@author: justing
"""
from os import path
import robin_stocks.robinhood as rh
import numpy as np
import pandas as pd
#from pandas_datareader import data as pdr
#yf.pdr_override()
import datetime as dt
import matplotlib.pyplot as plt

#%%

def call_login():
    fname_creds = 'creds_tok.pem'
    rpath_creds = './../'
    credspath = path.join(rpath_creds, fname_creds)
    
    if(path.exists(credspath)):
        with open(credspath) as infile:
            lins=infile.readlines()
        uid = lins[0].strip('\n')
        pid = lins[1].strip('\n')
        rh.authentication.login(username=uid, password=pid)

        del uid
        del pid
        del lins
        return True
    else:
        print("Credentials file not found. Check your path.")
        return False


def build_filepath():
    stock_orders_path='./'
    stock_orders_filehead='stock_orders_'
    file_date=dt.datetime.strftime(dt.datetime.now(tz=None),'%b-%d-%Y')
    file_extension='.csv'
    stock_orders_filename=stock_orders_filehead+file_date+file_extension
    return [stock_orders_path, stock_orders_filename]



def create_transactions():
    [csv_path, csv_file] = build_filepath()
    
    print(csv_path)
    print(csv_file)
    
    if(path.isfile(path.join(csv_path, csv_file))):
        print('Overwriting pre-existing file with updated transaction data.')
    
    rh.export.export_completed_stock_orders(dir_path=csv_path, file_name=csv_file)
    return


def import_transactions():
    [csv_path, csv_file] = build_filepath()    
    
    df_orders=pd.read_csv(path.join(csv_path, csv_file))
    df_orders.sort_values('date',inplace=True)
    df_orders.reset_index(inplace=True, drop=True)   #tz = UTC on data import
    return df_orders

  
def user_transaction_dataframe(ticker, df_import):
    df_return = df_import[df_import.symbol==ticker].sort_values('date')
    sell_qty=-df_return[df_return.side=='sell'].quantity
    
    # calculate cumulative holding and cost basis
    df_return.loc[sell_qty.index, 'quantity']=sell_qty.values
    outstanding_shares=np.round(df_return['quantity'].cumsum())
    
    df_return.insert(loc=6, column='outst_shares', value = np.round(df_return['quantity'].cumsum(),decimals=6))

#    df_return.loc[sell_qty.index, 'outst_shares']
# USEFUL TO REPLACE OUTST_SHARES=0 AT SELL EVENT, OTHERWISE INTRADAY TRADES ARE INVISIBLE IN P/L

    cost_basis_calc=((df_return['quantity']*df_return['average_price']).cumsum()).div(df_return['outst_shares'])
    df_return.insert(loc=8, column='cost_basis', value=cost_basis_calc)

    # clean up the divide-by-zero terms (np.inf) - replace np.inf with NaN temporarily
    idx=df_return.index[np.isinf(df_return['cost_basis'])]
    df_return.loc[idx,'cost_basis']=np.nan
    df_return['cost_basis'].fillna(method='ffill', inplace=True)
    idx=df_return[df_return['outst_shares']==0].index
    df_return.loc[idx,'cost_basis']=0.

    # drop un-needed rows and re-index
    df_return.drop(columns=['order_type','fees'],inplace=True)
    df_return.set_index(pd.to_datetime(df_return['date'], utc=True),inplace=True)
    df_return.drop(axis=1, columns='date',inplace=True)
    return df_return
    

def historical_dataframe(ticker):    
    list_history=rh.get_stock_historicals([ticker],interval='day',span='year')
    df_hist=pd.DataFrame(list_history, dtype=float)
    df_hist.set_index(pd.to_datetime(df_hist['begins_at'])+pd.Timedelta(value=12.75, unit='hours'),inplace=True, drop=True)
    df_hist.insert(loc=5, column='mid_price', value=0.5*(df_hist.open_price+df_hist.close_price))
    df_hist.drop(columns=['session','interpolated'], inplace=True)
    df_hist.index.rename('date',inplace=True)
    df_hist.rename(columns={'symbol':'symbol_hist'}, inplace=True)

    return df_hist
    
def join_dataframes(df_hist_data, df_user_trans):

    df_join = df_hist_data.join(df_user_trans, how='outer')
    df_join.insert(loc=11, column='PL_percentage',value=0.00)
    df_join.insert(loc=12, column='portfolio_percentage', value=float(0.00))
    df_join.drop(columns='symbol_hist', inplace=True)
    df_join['cost_basis'].fillna(method='ffill',inplace=True)
    df_join['mid_price'].fillna(method='ffill',inplace=True)
    df_join['outst_shares'].fillna(method='ffill',inplace=True)
    df_join['cost_basis'].fillna(value=0.0, inplace=True)
    df_join['outst_shares'].fillna(value=0.0, inplace=True)
    
    # assign PL_percentage where SIDE != NaN (i.e. SIDE=BUY|SELL)
    df_join.loc[df_sym.index, 'PL_percentage']=100.*(df_join['average_price']-df_join['cost_basis'])/(df_join['cost_basis'])

    # assign PL_percentage where SIDE = NaN (during normal historical record)
    df_join.loc[df_history.index, 'PL_percentage']=100.*(df_join['mid_price']-df_join['cost_basis'])/(df_join['cost_basis'])

#    df_join.loc[df_sym.index, 'portfolio_percentage']=df_join['mid_price']*df_join['outst_shares']
    df_join['portfolio_percentage']=(df_join['mid_price']*df_join['outst_shares']).astype(float)

    zero_idx=df_join.index[np.isinf(df_join['PL_percentage'])]
    df_join.loc[zero_idx,'PL_percentage']=1e-6
    
    return df_join

#%%
call_login()

#%%
orders_csv=create_transactions()

df_import_raw = import_transactions()

#%%
df_orders = df_import_raw

iter_count=0
df_multix = []

for sym_loop in df_orders.symbol.unique(): #df_orders.symbol:
    
    df_sym = user_transaction_dataframe(sym_loop, df_orders)
    
    df_history = historical_dataframe(sym_loop)

    df_join = join_dataframes(df_history, df_sym)
       
    
    columns_array = [list(np.full(len(df_join.columns),sym_loop)), list(df_join.columns)]
    df_multix.append(pd.DataFrame(df_join.values, index=df_join.index, columns=columns_array))

    iter_count = iter_count + 1

#%%
df_full = pd.concat(df_multix, axis=1, join='outer')

#%%
df_sector=pd.DataFrame({'sector':[], 'industry':[]})

for sym_loop in df_orders.symbol.unique(): #df_orders.symbol:
    fundy=rh.get_fundamentals([sym_loop])[0]
    df_sector.loc[sym_loop, 'sector']=fundy['sector'] 
    df_sector.loc[sym_loop, 'industry']=fundy['industry'] 
    df_sector.loc[sym_loop, 'rgb']=''
colors_list=[]
#%%
for u in df_sector.sector.unique():
    print(u)
#    colors_list.append(tuple(np.random.choice(range(256), size=3)/256.))
    idx=df_sector[df_sector.sector == u].index
#    print(idx)
    color_list=tuple(np.random.choice(range(256), size=3)/256.)
    for sym in idx:
#        print(sym, color_list)
        df_sector.loc[sym,'rgb']=color_list
#df_sector.insert(loc=2, column='rgb',value=colors_list)
#%%


#%%
### OVERPLOT ALL
for sym_df in df_multix:

    df_temp=sym_df

    sym_ticker=df_temp.columns[0][0]

    x_scatter = df_temp.index
    y_scatter = df_temp[sym_ticker]['PL_percentage']

    df_nonzeros=df_temp[sym_ticker]['portfolio_percentage'].values != 0.0
    x_scatter_nz = df_temp[df_nonzeros].index
    y_scatter_nz = df_temp[sym_ticker]['PL_percentage']
    plt.scatter(x_scatter, y_scatter, s=18, ec='black', alpha=.75, c=[df_sector.loc[sym_ticker,'rgb']]*len(x_scatter))
    
#    y_line = df_temp[df_temp.columns[0][0]]['mid_price']
#    plt.plot(x_scatter, y_line, c='black')
    plt.ylim(-40,40)

    xmin=pd.to_datetime(dt.datetime(2020, 12, 31, 23, 59, 0))
    xmax=pd.to_datetime(dt.datetime(2021, 8, 1, 0, 1, 0))
    plt.xlim(xmin,xmax)
    

plt.show()
#%%

# PLOT A SPECIFIC SECTOR
# Scatter plot colors are suppressed bc we want to visually differentiate b/w assets

sector_to_plot = 'Producer Manufacturing'
for sym_df in df_multix:
    
    df_temp=sym_df
    legend_syms=[]
    sym_ticker=df_temp.columns[0][0]
    if(df_sector.loc[sym_ticker, 'sector']==sector_to_plot and sym_ticker!='PLTR'):

#        legend_syms.append(sym_ticker)
        x_scatter = df_temp.index
        y_scatter = df_temp[sym_ticker]['PL_percentage']
        
        shares_mask=df_temp[sym_ticker]['outst_shares']
        
        scatter_size = df_temp[sym_ticker]['portfolio_percentage'].astype(float)
#        scatter_size=(df_temp[sym_ticker]['outst_shares']*df_temp[sym_ticker]['mid_price']).astype(float)
        
        plt.scatter(x_scatter, y_scatter.mask(shares_mask==0), s=3.0*scatter_size, ec='black', alpha=.75, label=sym_ticker)# , c=[df_sector.loc[sym_ticker,'rgb']]*len(x_scatter))
    
    #    y_line = df_temp[df_temp.columns[0][0]]['mid_price']
    #    plt.plot(x_scatter, y_line, c='black')
        plt.ylim(-40,40)
        plt.legend(loc='upper right', bbox_to_anchor=(1.32, 1.1))
        xmin=pd.to_datetime(dt.datetime(2020, 12, 31, 23, 59, 0))
        xmax=pd.to_datetime(dt.datetime(2021, 8, 1, 0, 1, 0))
        plt.xlim(xmin,xmax)
        

plt.show()




#%%
print((df_temp[sym_ticker]['outst_shares']*df_temp[sym_ticker]['mid_price']).astype(float))





