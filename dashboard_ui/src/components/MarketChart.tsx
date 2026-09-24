import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi } from "lightweight-charts";

type Candle = {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export function MarketChart({ candles }: { candles: Candle[] }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      layout: {
        background: { color: "#0e1626" },
        textColor: "#8fa0ba",
      },
      grid: {
        vertLines: { color: "#1c2740" },
        horzLines: { color: "#1c2740" },
      },
      width: ref.current.clientWidth,
      height: 280,
    });
    const series = chart.addCandlestickSeries({
      upColor: "#3ecf8e",
      downColor: "#e76f51",
      borderVisible: false,
      wickUpColor: "#3ecf8e",
      wickDownColor: "#e76f51",
    });
    chartRef.current = chart;
    seriesRef.current = series;
    const onResize = () => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth });
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.remove();
    };
  }, []);

  useEffect(() => {
    if (!seriesRef.current || !candles?.length) return;
    const data = candles.map((c) => ({
      time: Math.floor(new Date(c.timestamp).getTime() / 1000) as unknown as string,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
    // lightweight-charts expects UTCTimestamp numbers
    seriesRef.current.setData(data as never);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  return <div className="chart-box" ref={ref} />;
}
