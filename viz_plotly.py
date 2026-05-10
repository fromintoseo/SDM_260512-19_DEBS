
import plotly.graph_objects as go
import plotly.express as px
from typing import List
from model import Instance, ScheduledOp


def plot_gantt_plotly(instance: Instance, schedule: List[ScheduledOp], out_html: str = "gantt.html") -> None:
    fig = go.Figure()

    unique_jobs = sorted(list(set(op.job_id for op in schedule)))

    colors = px.colors.qualitative.Plotly
    job_colors = {job: colors[i % len(colors)] for i, job in enumerate(unique_jobs)}

    # M1, M2 ... 순으로 이름 목록 생성됨
    machine_names = [m.name for m in instance.machines]

    for op in schedule:
        duration = op.end - op.start
        assigned_machine_name = instance.machines[op.machine_id].name

        fig.add_trace(go.Bar(
            name=f"Job {op.job_id}",
            x=[duration],
            y=[assigned_machine_name],
            base=[op.start],
            orientation='h',
            marker_color=job_colors[op.job_id],
            text=f"J{op.job_id}-O{op.op_id}",
            textposition="inside",
            insidetextfont=dict(color='white'),
            hoverinfo="text",
            hovertext=(f"<b>Job {op.job_id} | Op {op.op_id}</b><br>"
                       f"Machine: {assigned_machine_name}<br>"
                       f"Start: {op.start}<br>"
                       f"End: {op.end}<br>"
                       f"Duration: {duration}"),
            showlegend=False
        ))

    for job_id in unique_jobs:
        fig.add_trace(go.Bar(
            name=f"Job {job_id}",
            x=[0],
            y=[machine_names[0]],
            base=[0],
            orientation='h',
            marker_color=job_colors[job_id],
            showlegend=True
        ))

    fig.update_layout(
        barmode='overlay',
        title="FJSP 간트 차트",
        xaxis_title="Time",
        yaxis_title="Machine",
        yaxis=dict(categoryorder='array', categoryarray=machine_names[::-1]),
        plot_bgcolor='white',
    )

    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='lightgray')

    fig.write_html(out_html)
    print(f"저장되었습니다: {out_html}")