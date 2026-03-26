import type Plotly from 'plotly.js-dist';

// Active orders histogram (horizontal bar)
export const orderHistogramOptions = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: { legend: { display: false } },
    scales: {
        x: { grid: { color: 'rgba(128,128,128,0.15)' }, ticks: { color: '#9ca3af', font: { size: 10 } } },
        y: { grid: { display: false }, ticks: { color: '#9ca3af', font: { size: 10 } } },
    },
};

// Order book histogram — vertical line at mid price
export const obMidPricePlugin = {
    id: 'obMidPriceLine',
    afterDraw(chart: any) {
        const mid = chart.options.plugins?.obMidPriceLine?.value;
        if (mid == null) return;
        const xAxis = chart.scales['x'];
        const yAxis = chart.scales['y'];
        if (!xAxis || !yAxis) return;
        const labels = (chart.data.labels as string[]).map(Number);
        if (labels.length === 0) return;
        let x: number;
        if (mid <= labels[0]) {
            x = xAxis.getPixelForValue(0);
        } else if (mid >= labels[labels.length - 1]) {
            x = xAxis.getPixelForValue(labels.length - 1);
        } else {
            let i = 0;
            while (i < labels.length - 1 && labels[i + 1] <= mid) i++;
            const t = (mid - labels[i]) / (labels[i + 1] - labels[i]);
            x = xAxis.getPixelForValue(i) + t * (xAxis.getPixelForValue(i + 1) - xAxis.getPixelForValue(i));
        }
        const ctx = chart.ctx;
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x, yAxis.top);
        ctx.lineTo(x, yAxis.bottom);
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = '#facc15';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();
    },
};

export function getObHistogramOptions(midPrice: number | null, visibleLabels: string[]) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
            legend: { labels: { color: '#9ca3af', font: { size: 10 } } },
            obMidPriceLine: { value: midPrice },
        },
        scales: {
            x: {
                grid: { display: false },
                ticks: {
                    color: '#9ca3af',
                    font: { size: 10 },
                    callback(this: any, value: any) {
                        const label = this.getLabelForValue(value);
                        return visibleLabels.includes(label) ? label : null;
                    },
                },
            },
            y: { grid: { color: 'rgba(128,128,128,0.15)' }, ticks: { color: '#9ca3af', font: { size: 10 } } },
        },
    };
}

// Price chart (Plotly)
export const plotLayout: Partial<Plotly.Layout> = {
    margin: { t: 10, r: 10, b: 40, l: 50 },
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    font: { color: '#9ca3af' },
    xaxis: {
        showgrid: false,
        tickfont: { size: 11 },
        nticks: 6,
    },
    yaxis: {
        gridcolor: 'rgba(128,128,128,0.15)',
        tickfont: { size: 11 },
        zerolinecolor: 'rgba(128,128,128,0.2)',
    },
    legend: { orientation: 'h', y: 1.12, x: 0 },
    hovermode: 'x unified',
};

export const plotConfig: Partial<Plotly.Config> = {
    responsive: true,
    displayModeBar: false,
};
