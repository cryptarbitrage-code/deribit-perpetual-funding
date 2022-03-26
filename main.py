from tkinter import *
import datetime
from datetime import date, timedelta
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg, NavigationToolbar2Tk)
from api_functions import get_funding_rate_history
from ratelimiter import RateLimiter

# to do:
# change to 8 hour data

# Some chart parameters
chart_size = (12, 6)

# tkinter set up
root = Tk()
root.title("Option Visualiser - Cryptarbitrage")
root.iconbitmap('cryptarbitrage_icon_96px.ico')
root.minsize(600, 400)

# Details frame
details_frame = LabelFrame(root, text="Details", padx=2, pady=2)
details_frame.grid(row=0, column=0, padx=2, pady=2, sticky=NW)
# Chart frames
chart1_frame = LabelFrame(root, text="Profit/Loss", padx=2, pady=2)
chart1_frame.grid(row=0, column=1, rowspan=2, padx=2, pady=2)

DAY = 24*60*60  # day in seconds
oldest_date = 1556668800000  # the furthest we will look back, 1556668800000 = 1st May 2019 00:00
all_timestamps = []
first_day_of_month = date.today().replace(day=1)  # initially set to day 1 of current the month
first_day_timestamp = (first_day_of_month - date(1970, 1, 1)).days * DAY * 1000
all_timestamps.append(first_day_timestamp)
# add timestamps for start of each month going back to oldest_date
while not first_day_timestamp == oldest_date:
    last_day_of_prev_month = first_day_of_month.replace(day=1) - timedelta(days=1)
    first_day_of_month = last_day_of_prev_month.replace(day=1)
    first_day_timestamp = (first_day_of_month - date(1970, 1, 1)).days * DAY * 1000
    all_timestamps.append(first_day_timestamp)

print(all_timestamps)
print(len(all_timestamps))


@RateLimiter(max_calls=5, period=1)
def get_funding_data(instrument, start_timestamp, end_timestamp):
    print('attempt')
    # pulls in funding history data
    funding_data = get_funding_rate_history(instrument, start_timestamp, end_timestamp)
    dates = []
    h1_interest = []
    for entry in funding_data:
        date_value = datetime.datetime.utcfromtimestamp(entry['timestamp']/1000)
        dates.append(date_value)
        h1_interest.append(entry['interest_1h'])

    dates.reverse()
    h1_interest.reverse()

    return dates, h1_interest


def plot_charts():
    # Destroy old charts if any
    for widgets in chart1_frame.winfo_children():
        widgets.destroy()

    x_range_all = []
    h1_interest_all = []
    for month in range(0, len(all_timestamps)-1):
        instrument = selected_instrument.get()
        if all_timestamps[month + 1]:
            x_range, h1_interest = get_funding_data(instrument, all_timestamps[month], all_timestamps[month + 1])
            for time in x_range:
                x_range_all.append(time)
            for interest in h1_interest:
                h1_interest_all.append(interest)

    x_range_all.reverse()
    h1_interest_all.reverse()

    #h1_interest_np = np.array(h1_interest)
    #zero_np = np.array([0] * number_of_datapoints)

    # CHART 1
    # the figure that will contain the plot
    fig1 = Figure(figsize=chart_size, dpi=100)
    # adding the subplot
    plot1 = fig1.add_subplot(111)
    # plotting the graph
    plot1.plot(x_range_all, h1_interest_all, linewidth=2, label='Funding rate')
    #plot1.fill_between(x_range, h1_interest, 0, where=(h1_interest_np < zero_np), facecolor='red', interpolate=True, alpha=0.15)
    #plot1.fill_between(x_range, h1_interest, 0, where=(h1_interest_np >= zero_np), facecolor='green', interpolate=True, alpha=0.15)
    plot1.set_xlabel('Time/Date')
    plot1.set_ylabel('Funding Rate')
    # plot1.set_title('Chart Title')
    plot1.legend()
    plot1.grid(True, alpha=0.25)
    fig1.autofmt_xdate()
    fig1.tight_layout()
    # creating the Tkinter canvas
    # containing the Matplotlib figure
    canvas1 = FigureCanvasTkAgg(fig1, master=chart1_frame)
    canvas1.draw()
    # placing the canvas on the Tkinter window
    canvas1.get_tk_widget().pack()
    # creating the Matplotlib toolbar
    toolbar = NavigationToolbar2Tk(canvas1, chart1_frame)
    toolbar.update()
    # placing the toolbar on the Tkinter window
    canvas1.get_tk_widget().pack()

    plt.show()


# details_frame components
selected_instrument = StringVar()
selected_instrument.set("BTC-PERPETUAL")
instrument_label = Label(details_frame, text="Instrument: ")
instrument_label.grid(row=0, column=0)
instrument_dropdown = OptionMenu(details_frame, selected_instrument, "BTC-PERPETUAL", "ETH-PERPETUAL")
instrument_dropdown.grid(row=0, column=1)
instrument_dropdown.config(width=10)

start_time_label = Label(details_frame, text="Start Time: ")
start_time_label.grid(row=1, column=0)
start_time_input = Entry(details_frame, width=15)
start_time_input.grid(row=1, column=1, padx=5, pady=5)

end_time_label = Label(details_frame, text="End Time: ")
end_time_label.grid(row=2, column=0)
end_time_input = Entry(details_frame, width=15)
end_time_input.grid(row=2, column=1, padx=5, pady=5)

# button that displays the plot
plot_button = Button(master=details_frame,
                     command=plot_charts,
                     height=2,
                     width=10,
                     text="Plot",
                     bg="#88bb88")

plot_button.grid(row=4, column=1)

root.mainloop()