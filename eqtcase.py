import streamlit as st
import numpy as np
import requests
import plotly.express as px
import pandas as pd
from datetime import datetime, timedelta

# Streamlit UI for date input
st.title('EQT Case Analysis')
st.header('Introduction')
st.write('We are given a dataset which we can extract with repeated API calls, calling 20 at a time, until all data is retrieved for dates 01/01/2024 - 04/03/2024')

start_date = datetime(2024, 1, 1)
end_date = datetime(2024, 3, 3)  # Only 9 weeks data (no data on Monday week 10)

# Create a DataFrame with weekly date ranges
date_range = pd.date_range(start=start_date, end=end_date, freq='W-MON') # Week filtering more usable than date
weeks = [(f"Week {i+1}", date) for i, date in enumerate(date_range)] 

selected_weeks = st.multiselect("Select Week(s)", options=[week[0] for week in weeks]) # streamlit multi select widget

# Map selected weeks to corresponding dates
if selected_weeks:
    selected_indices = [int(week.split()[1]) - 1 for week in selected_weeks] # adjust 0 indexing
    selected_start_date = weeks[min(selected_indices)][1]  
    selected_end_date = weeks[max(selected_indices)][1] + timedelta(days=6)
    formatted_start_date = selected_start_date.strftime('%Y-%m-%d')
    formatted_end_date = selected_end_date.strftime('%Y-%m-%d')
    st.write(f"Selected weeks correspond to the following date range: {formatted_start_date} to {formatted_end_date}")
else:
    selected_start_date = start_date
    selected_end_date = end_date

@st.cache_data
def fetch_data():
    start_date = datetime(2024, 1, 1)
    end_date = datetime(2024, 3, 4)
    all_data = []
    
    # Loop in 20-day intervals
    while start_date <= end_date:
        next_end_date = start_date + timedelta(days=19)  # 20 days max fetch
        adjusted_end_date = min(next_end_date + timedelta(days=1), end_date + timedelta(days=1))  # Adjust for end indexing
        
        url = f"https://script.google.com/macros/s/AKfycbz1LM_uFB2TTLg-9QyVJScP-ztimFXXBJGxPFoFTN4Jfe_rgFVf/exec?start_date={start_date.strftime('%Y-%m-%d')}&end_date={adjusted_end_date.strftime('%Y-%m-%d')}"
        
        response = requests.get(url)
        if response.json().get('ok'):
            print(f"Fetched data from {start_date.strftime('%Y-%m-%d')} to {adjusted_end_date.strftime('%Y-%m-%d')}")
            all_data.extend(response.json()['data'])
        else:
            print(f"Failed to fetch data from {start_date.strftime('%Y-%m-%d')} to {next_end_date.strftime('%Y-%m-%d')}")
        
        start_date = next_end_date + timedelta(days=1)
    
    # Save in df and export to excel as backup
    df = pd.DataFrame(all_data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"]) # ensure usable date formatting
        df = df.sort_values(by="date")
        df.to_excel("usage data.xlsx", index=False)
        print("Data exported")
    else:
        print("df empty")
    return df

df_all = fetch_data()

if not df_all.empty: # safety
    st.header('Task 1')
    st.subheader('KPI Review')

    # Calculate weeks and cohorts
    df_all['week'] = df_all['date'].dt.isocalendar().week
    df_all['cohort_week'] = df_all.groupby('user_id')['week'].transform('min') # new column that identifies first week a user joined
    df_all['first_activity_date'] = df_all.groupby('user_id')['date'].transform('min') # day level precision
    
    df_all['is_new_user'] = df_all['date'] == df_all['first_activity_date'] # for seasonlity trend, defined in df_all

    df = df_all[(df_all['date'] >= selected_start_date) & (df_all['date'] <= selected_end_date)] # filter based on st selection

    if not df.empty:
        dau = df.groupby("date")["user_id"].nunique().reset_index(name="DAU")
        wau = df.groupby('week')["user_id"].nunique().reset_index(name="WAU")
        
        df['is_new_user'] = df['date'] == df['first_activity_date']
        new_users = df[df['is_new_user']].groupby('week')['user_id'].nunique().reset_index()
        new_users.columns = ["week", "New Users"] # next time better rename week :/ 
        
        growth_df = pd.merge(wau, new_users, on="week", how="left")
        
        growth_df["New Users"].fillna(0, inplace=True) # eliminate NAs, 0 fine

        # Calculate users who became inactive since last week
        growth_df["Prev WAU"] = growth_df["WAU"].shift(1, fill_value=0)
        growth_df["Users Inactive"] = growth_df["Prev WAU"] + growth_df["New Users"] - growth_df["WAU"]

        # Plots
        st.subheader("Daily Active Users Over Time")
        fig_dau = px.line(dau, x="date", y="DAU", title="Daily Active Users Over Time")
        fig_dau.update_layout(
            xaxis=dict(title="Day", showgrid=True, gridcolor='lightgray'),
            yaxis=dict(showgrid=True, gridcolor='lightgray'),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        st.plotly_chart(fig_dau)
        
        st.subheader("WAU, New Users, and Inactive Users")
        fig_growth = px.line(growth_df, x="week", y=["WAU", "New Users", "Users Inactive"], title="WAU, New Users, and Inactive Users", markers=True)
        fig_growth.update_layout(
            xaxis=dict(title="Week", showgrid=True, gridcolor='lightgray'),
            yaxis=dict(title="Value", showgrid=True, gridcolor='lightgray'),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        st.plotly_chart(fig_growth)

        # Calculate percentage change KPI 
        growth_df["WAU_pct_change"] = growth_df["WAU"].pct_change().fillna(0) * 100
        growth_df["New_Users_pct_change"] = growth_df["New Users"].pct_change().fillna(0) * 100
        growth_df["Users_Inactive_pct_change"] = growth_df["Users Inactive"].pct_change().fillna(0) * 100

        growth_df.replace([np.inf, -np.inf], 100, inplace=True) # inactivity increase from 0

        growth_df = growth_df.round({
            "WAU_pct_change": 0,
            "New_Users_pct_change": 0,
            "Users_Inactive_pct_change": 0
        })

        kpi_table = growth_df[["week", "WAU_pct_change", "New_Users_pct_change", "Users_Inactive_pct_change"]].set_index('week').T
        kpi_table = kpi_table.applymap(lambda x: f"{x:.0f}%")

        st.subheader("Week-over-Week Percentage Change in WAU, New Users, and Users Inactive")
        st.dataframe(kpi_table)

        # Create weekday for seasonlity check
        df_all['weekday'] = df_all['date'].dt.day_name()

        total_users_by_weekday = df_all.groupby('weekday')['user_id'].nunique().reset_index(name="Total Users")
        new_users_by_weekday = df_all[df_all['is_new_user']].groupby('weekday')['user_id'].nunique().reset_index(name="New Signups")
        weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] # sort for viewing
        total_users_by_weekday['weekday'] = pd.Categorical(total_users_by_weekday['weekday'], categories=weekday_order, ordered=True) # workaround so no weekdays not sorted alphabetically
        new_users_by_weekday['weekday'] = pd.Categorical(new_users_by_weekday['weekday'], categories=weekday_order, ordered=True)

        weekday_analysis = pd.merge(total_users_by_weekday, new_users_by_weekday, on='weekday', how='left') # merge
        weekday_analysis.sort_values(by="weekday", inplace=True)

        st.subheader("User Activity by Weekday")
        st.dataframe(weekday_analysis)

        st.write("Total usage is generally even throughout the week, with a drop in Wednesday. Sign-ups clearly take place at the start/earlier in the week")



        st.header('Task 2')
        st.subheader("Profitability Overview")
        st.write("Note, plots and data look at all data, and is not impacted by chosen weeks")
        st.write('Here we look at the profitability of the business. We can first quickly look at answering "is the business profitable today?". The answer is no.')
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("#### Current Revenue")
            st.markdown("<h2 style='text-align: center; font-size: 30px;'>€1,542</h2>", unsafe_allow_html=True) # manually done

        with col2:
            st.markdown("#### Marketing Spend")
            st.markdown("<h2 style='text-align: center; font-size: 30px;'>€2,000</h2>", unsafe_allow_html=True)

        with col3:
            st.markdown("#### Profit")
            st.markdown("<h2 style='text-align: center; font-size: 30px;'>-€458</h2>", unsafe_allow_html=True)
        
        st.write("In total we had 771 weekly users, each bringing in €2 on average a week => €1,542, compared to the marketing spend of €2,000, over the 9 weeks.")
        st.write("**However, we don't go further than this, because we know this is not the full story! We care about LTV most, especially from an investability perspective...**")

        # Cohort analysis (LTV vs CAC)
        cohorts_wau = df_all.groupby(['cohort_week', 'week'])['user_id'].nunique().reset_index() # get week active and week first active
        cohorts_wau.columns = ['Cohort Week', 'Week', 'Weekly Active Users']

        cohort_sizes = cohorts_wau.groupby(['Cohort Week', 'Week'])['Weekly Active Users'].sum().reset_index()
        cohort_sizes.columns = ['Cohort Week', 'Week', 'User Count']

        week_1_sizes_all = cohort_sizes[cohort_sizes['Week'] == cohort_sizes['Cohort Week']].set_index('Cohort Week')['User Count']
        week_9_sizes_all = cohort_sizes[cohort_sizes['Week'] == 9].set_index('Cohort Week')['User Count']
        
        cohort_growth_all = pd.merge(week_1_sizes_all, week_9_sizes_all, how='left', on='Cohort Week', suffixes=('_firstWeek', '_week9'))
        
        # Calculate average churn for each cohort
        average_churn_per_cohort = {}
        for cohort_week in cohort_growth_all.index:
            weeks_active = (9 - cohort_week)
            initial_users = cohort_growth_all.loc[cohort_week, 'User Count_firstWeek']
            final_users = cohort_growth_all.loc[cohort_week, 'User Count_week9']
            churn_rate = 1 - (final_users / initial_users) ** (1/weeks_active) if initial_users > 0 and final_users > 0 else 0
            average_churn_per_cohort[cohort_week] = churn_rate
        average_churn_per_cohort[9] = (average_churn_per_cohort[8] + average_churn_per_cohort[7] + average_churn_per_cohort[6]) / 3  # assume last 3 cohort churns apply to cohort 9

        print(average_churn_per_cohort)

        ltv_per_cohort = {cohort_week: 2 / churn_rate if churn_rate != 0 else 0 for cohort_week, churn_rate in average_churn_per_cohort.items()}
        new_users_per_cohort = df_all.groupby('cohort_week')['user_id'].nunique()  # Use df_all here 
        
        total_marketing_spend = 2000
        cac_per_cohort = {}
        for cohort_week, new_users in new_users_per_cohort.items():
            cac = total_marketing_spend / 9 / new_users
            cac_per_cohort[cohort_week] = cac
        
        data = pd.DataFrame({
            'Cohort Week': list(ltv_per_cohort.keys()),
            'LTV': list(ltv_per_cohort.values()),
            'CAC': list(cac_per_cohort.values())
        })
        
        st.subheader("LTV vs CAC by Cohort")
        st.write("This chart is based on all available data and does not change with date/week inputs.")

        fig_ltv_cac = px.line(data.melt('Cohort Week', var_name='Metric', value_name='Value'),
                            x='Cohort Week', y='Value', color='Metric', markers=True, title="LTV vs CAC by Cohort")
        fig_ltv_cac.update_layout(
            xaxis=dict(title="Cohort Week", showgrid=True, gridcolor='lightgray'),
            yaxis=dict(title="Value", showgrid=True, gridcolor='lightgray'),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        st.plotly_chart(fig_ltv_cac)
        st.write("We assumed that cohort 9 would experience similar churn as the average weekly churn of cohorts 6, 7, 8. It can equally be argued that cohort 8 has limited churn data, but we used its one week as our churn nonetheless")


        st.subheader("User Count per Cohort across Weeks")
        fig_cohorts = px.line(cohorts_wau, x="Week", y="Weekly Active Users", color="Cohort Week",
                              title="User Count per Cohort across Weeks", markers=True)
        fig_cohorts.update_layout(
            xaxis=dict(title="Week", showgrid=True, gridcolor='lightgray'),
            yaxis=dict(title="Weekly Active Users", showgrid=True, gridcolor='lightgray'),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        st.plotly_chart(fig_cohorts)

        data['LTV'] = data['LTV'].round(2)
        data['CAC'] = data['CAC'].round(2)
        data['New Users'] = new_users_per_cohort.reindex(data['Cohort Week']).values
        data['Total LTV'] = (data['LTV'] * data['New Users']).round(0)
        data['Total CAC'] = (data['CAC'] * data['New Users']).round(0)
        data['LTV/CAC'] = (data['Total LTV'] / data['Total CAC']).round(1)
        
        st.subheader("Total LTV by Cohort")
        st.write("The table below shows the total LTV and CAC for each cohort (LTV/CAC per user * the number of new users). LTV and CAC in €.")
        st.dataframe(data[['Cohort Week', 'LTV', 'CAC', 'Total LTV', 'Total CAC', 'LTV/CAC']])

        sum_LTV = data['Total LTV'].sum()
        sum_CAC = data['Total CAC'].sum()
        average_LTVCAC = (sum_LTV / sum_CAC).round(1)

        st.subheader("Adjusted Profitability View (for the 9 Weeks)")

        col4, col5, col6 = st.columns(3)
        with col4:
            st.markdown("#### LTV")
            st.markdown(f"<h2 style='text-align: center; font-size: 30px;'>€{sum_LTV:,.0f}</h2>", unsafe_allow_html=True)

        with col5:
            st.markdown("#### Marketing Spend")
            st.markdown(f"<h2 style='text-align: center; font-size: 30px;'>€2000</h2>", unsafe_allow_html=True)

        with col6:
            st.markdown("#### LTV/CAC")
            st.markdown(f"<h2 style='text-align: center; font-size: 30px;'>{average_LTVCAC:,.1f}</h2>", unsafe_allow_html=True)

        st.write("We see an LTV/CAC of 2.5, which is less than the base VC expectation of 3, particularly if we have high standard - expecting values of 4 or 5 +")
        st.write("LTV/CAC does improve nicely throughout the cohorts, which offers promise. We can discuss this more together :)")

        
        df_all.to_excel("final excel doc.xlsx", index=False)
    else:
        st.write("Filtered data empty")
else:
    st.write("Original fetched data is empty, check source")
