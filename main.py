from tkinter import *
import datetime
from datetime import date, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, NavigationToolbar2Tk)
from api_functions import get_funding_rate_history
from ratelimiter import RateLimiter

# Some chart parameters
chart_size = (12, 4)

# tkinter set up
root = Tk()
root.title("Option Visualiser - Cryptarbitrage")
root.iconbitmap('cryptarbitrage_icon_96px.ico')
root.minsize(400, 200)

# Details frame
details_frame = LabelFrame(root, text="Details", padx=2, pady=2)
details_frame.grid(row=0, column=0, padx=2, pady=2, sticky=NW)
# Chart frames
chart1_frame = LabelFrame(root, text="Historical Funding", padx=2, pady=2)
chart1_frame.grid(row=0, column=1, rowspan=2, padx=2, pady=2)
chart2_frame = LabelFrame(root, text="Monthly Funding Totals", padx=2, pady=2)
chart2_frame.grid(row=2, column=1, padx=2, pady=2)

DAY = 24*60*60  # day in seconds
oldest_date = 1556668800000  # time that data will be collected back to, 1556668800000 = 1st May 2019 00:00
all_timestamps = []
first_day_of_month = date.today().replace(day=1)  # initially set to day 1 of current the month
first_day_timestamp = (first_day_of_month - date(1970, 1, 1)).days * DAY * 1000
all_timestamps.append(first_day_timestamp)
# add timestamps for start of each month going back to oldest_date
while first_day_timestamp > oldest_date:
    last_day_of_prev_month = first_day_of_month.replace(day=1) - timedelta(days=1)
    first_day_of_month = last_day_of_prev_month.replace(day=1)
    first_day_timestamp = (first_day_of_month - date(1970, 1, 1)).days * DAY * 1000
    all_timestamps.append(first_day_timestamp)

all_timestamps.reverse()  # put timestamps in chronological order

print(all_timestamps)
print(len(all_timestamps))


@RateLimiter(max_calls=5, period=1)
def get_funding_data(instrument, start_timestamp, end_timestamp):
    print('get_funding_data cycle', start_timestamp, end_timestamp)
    # pulls in funding history data
    funding_data = get_funding_rate_history(instrument, start_timestamp, end_timestamp)
    dates = []
    h8_interest = []
    for entry in funding_data:
        date_value = datetime.datetime.utcfromtimestamp(entry['timestamp']/1000)
        dates.append(date_value)
        h8_interest.append(entry['interest_8h'] * 100)  # also changes value from decimal to percentage

    #print('length of dates: ', len(dates))
    #print('length of h8 interest: ', len(h8_interest))
    # slice lists to get every 8th hour
    # slice should be [7::8] to cover month properly but Deribit api data is so off when set to 7
    dates_sliced = dates[6::8]
    h8_interest_sliced = h8_interest[6::8]
    print('h8 interest sliced: ', h8_interest_sliced)
    print('sum of 8h interest: ', sum(h8_interest_sliced))

    return dates_sliced, h8_interest_sliced


def plot_charts():
    # Destroy old charts if any
    for widgets in chart1_frame.winfo_children():
        widgets.destroy()
    for widgets in chart2_frame.winfo_children():
        widgets.destroy()

    # x-axis formatting
    month_locator = mdates.MonthLocator()
    quarterly_locator = mdates.MonthLocator(interval=3)

    x_range_all = []
    h8_interest_all = []
    months = []
    monthly_funding_totals = []
    for month in range(0, len(all_timestamps)-1):
        instrument = selected_instrument.get()
        if all_timestamps[month + 1]:
            x_range, h8_interest = get_funding_data(instrument, all_timestamps[month], all_timestamps[month + 1])
            months.append(datetime.datetime.utcfromtimestamp(all_timestamps[month]/1000))
            monthly_funding_totals.append(sum(h8_interest))
            for time in x_range:
                x_range_all.append(time)
            for interest in h8_interest:
                h8_interest_all.append(interest)

    print(len(h8_interest_all))
    h8_interest_np = np.array(h8_interest_all)
    zero_np = np.array([0] * len(h8_interest_all))

    # CHART 1: 8 hour historical funding rates
    # the figure that will contain the plot
    fig1 = Figure(figsize=chart_size, dpi=100)
    # adding the subplot
    plot1 = fig1.add_subplot(111)
    # plotting the graph
    plot1.plot(x_range_all, h8_interest_all, linewidth=0.5, label='Funding rate')
    plot1.fill_between(x_range_all, h8_interest_all, 0, where=(h8_interest_np < zero_np), facecolor='red', interpolate=True, alpha=0.15)
    plot1.fill_between(x_range_all, h8_interest_all, 0, where=(h8_interest_np >= zero_np), facecolor='green', interpolate=True, alpha=0.15)
    plot1.set_xlabel('Date')
    plot1.set_ylabel('Funding Rate %/8 Hours')
    # plot1.set_title('Chart Title')
    plot1.legend()
    plot1.grid(True, alpha=0.25)
    # x-axis formatting
    plot1.xaxis.set_minor_locator(month_locator)
    plot1.xaxis.set_major_locator(quarterly_locator)

    fig1.autofmt_xdate()
    fig1.tight_layout()
    # creating the Tkinter canvas containing the Matplotlib figure
    canvas1 = FigureCanvasTkAgg(fig1, master=chart1_frame)
    canvas1.draw()
    # placing the canvas on the Tkinter window
    canvas1.get_tk_widget().pack()
    # creating the Matplotlib toolbar
    toolbar = NavigationToolbar2Tk(canvas1, chart1_frame)
    toolbar.update()
    # placing the toolbar on the Tkinter window
    canvas1.get_tk_widget().pack()

    # CHART 2: Monthly funding totals
    # the figure that will contain the plot
    fig2 = Figure(figsize=chart_size, dpi=100)
    # adding the subplot
    plot2 = fig2.add_subplot(111)
    plot2_colours = ["red" if i < 0 else "green" for i in monthly_funding_totals]
    # plotting the graph
    plot2.bar(months, monthly_funding_totals, width=4, label='Funding rate', color=plot2_colours)
    plot2.set_xlabel('Date')
    plot2.set_ylabel('Funding Total %')
    plot2.grid(True, alpha=0.25)
    # x-axis formatting
    plot2.xaxis.set_minor_locator(month_locator)
    plot2.xaxis.set_major_locator(quarterly_locator)

    fig2.autofmt_xdate()
    fig2.tight_layout()

    # creating the Tkinter canvas containing the Matplotlib figure
    canvas2 = FigureCanvasTkAgg(fig2, master=chart2_frame)
    canvas2.draw()
    # placing the canvas on the Tkinter window
    canvas2.get_tk_widget().pack()
    # creating the Matplotlib toolbar
    toolbar = NavigationToolbar2Tk(canvas2, chart2_frame)
    toolbar.update()
    # placing the toolbar on the Tkinter window
    canvas2.get_tk_widget().pack()

    plt.show()


# details_frame components
selected_instrument = StringVar()
selected_instrument.set("BTC-PERPETUAL")
instrument_label = Label(details_frame, text="Instrument: ")
instrument_label.grid(row=0, column=0)
instrument_dropdown = OptionMenu(details_frame, selected_instrument, "BTC-PERPETUAL", "ETH-PERPETUAL")
instrument_dropdown.grid(row=0, column=1)
instrument_dropdown.config(width=16)

# button that displays the plot
plot_button = Button(master=details_frame,
                     command=plot_charts,
                     height=1,
                     width=18,
                     text="Plot",
                     bg="#88bb88")

plot_button.grid(row=4, column=1)

root.mainloop()
