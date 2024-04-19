import argparse
import os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import random
import requests

from datetime import datetime, timedelta
from dateutil import parser
from dotenv import load_dotenv
from plotly.subplots import make_subplots


load_dotenv()

JIRA_USERNAME = os.getenv('JIRA_USERNAME')
JIRA_API_KEY = os.getenv('JIRA_API_KEY')
JIRA_BASE_URL = os.getenv('JIRA_BASE_URL')
JIRA_STORY_POINT_FIELD_ID = os.getenv('JIRA_STORY_POINT_FIELD_ID')

AUTO_OPEN_FORECAST=os.getenv('AUTO_OPEN_FORECAST', True)


def get_tickets(sesh, query):
    
    base_url = f'{JIRA_BASE_URL}/rest/api/3'

    headers = {
        "Accept": "application/json"
    }
    
    query = {
        'jql': query,
        'maxResults': 1000
    }

    response = sesh.get(
        f'{base_url}/search',
        headers=headers,
        params=query
    ) 
    
    # print(response)
    data = response.json()
    print(data)
            
    tickets = []
    for i in data['issues']:
        tickets += [{
            'key': i['key'],
            'status': i['fields']['status']['name'],
            'story_points': i['fields'][JIRA_STORY_POINT_FIELD_ID],
            'status_changed_at': parser.parse(i['fields']['statuscategorychangedate']).date() # when it was moved to the current status
        }]
    
    df = pd.DataFrame(tickets)
    print(df)
    return df


def random_select_week_day(now, days_back):
    past_date = None
    while past_date is None:
        rand_number_days_back = random.randint(1, days_back)
        past_date = now - timedelta(days=rand_number_days_back)
        if past_date.weekday() == 5 or past_date.weekday() == 6:
            past_date = None

    return past_date


def run_daily_simulation(now, tickets_total, days_back, completed_ticket_dates):
    xmas_start = datetime.strptime('2022-12-20', '%Y-%m-%d').date()
    xmas_end = datetime.strptime('2023-01-04', '%Y-%m-%d').date()

    total_left = tickets_total
    final_date = None
    i = 0
    while total_left > 0:
        d = now + timedelta(days=i)
        not_xmas = not (xmas_start <= d <= xmas_end)
        if d.weekday() != 5 and d.weekday() != 6 and not_xmas:
            past_date = random_select_week_day(now, days_back)
            ticket_completed = completed_ticket_dates.get(past_date, 0)
            total_left = total_left - ticket_completed  # randomly select a past number of tickets closed
            final_date = d

        i += 1

    return final_date


def run_monte_carlo_simulation(issues_df):
    
    done_df = issues_df[issues_df['status'] == 'Done']
    not_done_df = issues_df
    not_done_df = not_done_df[not_done_df['status'] != 'Done']
    not_done_df = not_done_df[not_done_df['status'] != 'No Longer Relevant']
    
    print(done_df)
    print(not_done_df)
    
    story_points_remaining = not_done_df['story_points'].sum()
    days_back=30
    run_date = datetime.now().date().replace(2024, 3, 13)
    
    min_date = run_date - timedelta(days=days_back)
    closed_dates = done_df.groupby(by=['status_changed_at'])['story_points'].sum()
    filtered = closed_dates[closed_dates.index > min_date]
    dates = filtered.to_dict()

    print(f'story points remaining: {story_points_remaining}')
    results = []
    simulation_iters = 1000
    for i in range(0, simulation_iters):
        results += [{'date': run_daily_simulation(run_date, story_points_remaining, days_back, dates)}]
        

    completion_dates = pd.DataFrame(results)
    completion_date_counts = completion_dates.groupby(by=['date'])['date'].count()
    completion_date_counts = completion_date_counts.to_frame()

    completion_date_counts['index1'] = completion_date_counts.index
    completion_date_counts = completion_date_counts.reset_index(drop=True)
    completion_date_counts.columns = ['number_of_completes', 'date']
    
    print('std', completion_date_counts['number_of_completes'].std())
    print('mean', completion_date_counts['number_of_completes'].mean())

    confidences_by_date = completion_date_counts
    confidences_by_date['confidence'] = confidences_by_date['number_of_completes'].cumsum() / simulation_iters * 100

    expected_delivery_to_desired_confidence = confidences_by_date[confidences_by_date['confidence'] > 70].iloc[0]['date']
    print(f"Delivery date (70% confidence): {expected_delivery_to_desired_confidence}")

    # render
    subfig = make_subplots(specs=[[{"secondary_y": True}]])

    fig = px.bar(completion_date_counts, x='date', y='number_of_completes')
    fig2 = px.line(confidences_by_date, x='date', y='confidence', color_discrete_sequence=["rgb(255, 165, 0)"])

    fig2.update_traces(yaxis="y2")

    subfig.add_traces(fig.data + fig2.data)
    subfig.layout.xaxis.title = "Date"
    subfig.layout.yaxis.title = "Number of completes"
    subfig.layout.yaxis2.title = "Confidence"
    subfig.update_yaxes(rangemode='tozero')

    subfig.write_html('outputs/monte_carlo_forecast.html', auto_open=AUTO_OPEN_FORECAST)
   

def main(): 
    parser = argparse.ArgumentParser()
    parser.add_argument("--jql-query", type=str, required=True, help="jql query to pull the issues you require")
    args = parser.parse_args()
    
    session = requests.Session()
    session.auth = (JIRA_USERNAME, JIRA_API_KEY)
    
    issues = get_tickets(session, args.jql_query)
    
    run_monte_carlo_simulation(issues) 
    
if __name__ == '__main__':
    main()
    