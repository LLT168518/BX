# -*- coding: utf-8 -*-
import math, os
from datetime import datetime
from comtrade import (
    ComtradeConfig, AnalogChannel, DigitalChannel, SampleRate,
    ComtradeSample, ComtradeRecord, save_comtrade
)


def make_sample(out_dir: str):
    os.makedirs(out_dir, exist_ok=True)
    cfg = ComtradeConfig(
        station_name="110kV隆铭线保护",
        device_id="PL2202B",
        rev_year="1999",
        frequency=50.0,
        data_type="ASCII",
        time_mult=1.0,
        start_time=datetime(2019, 3, 4, 19, 18, 35),
        trigger_time=datetime(2019, 3, 4, 19, 18, 35, 138000),
        sample_rates=[SampleRate(rate=1200.0, end_sample=100)],
    )
    for i, (name, unit, a, b) in enumerate([
        ("保护电流A相(IA)", "A", 0.0043641976368280, 0.0),
        ("保护电流B相(IB)", "A", 0.0043641976368280, 0.0),
        ("保护电流C相(IC)", "A", 0.0043641976368280, 0.0),
        ("保护电压A相(UA)", "V", 0.0201080764926741, 0.0),
        ("保护电压B相(UB)", "V", 0.0201080764926741, 0.0),
        ("保护电压C相(UC)", "V", 0.0201080764926741, 0.0),
    ], start=1):
        cfg.analog_channels.append(AnalogChannel(
            index=i, name=name, phase=name[-3], unit=unit,
            a=a, b=b, min_val=-32767, max_val=32767,
            primary=1.0, secondary=1.0, ps="S"))
    cfg.analog_count = len(cfg.analog_channels)

    for i, name in enumerate(["总启动", "保护启动", "A相跳闸动作"], start=1):
        cfg.digital_channels.append(DigitalChannel(
            index=i, name=name, phase="", normal_state=0))
    cfg.digital_count = len(cfg.digital_channels)
    cfg.total_channels = cfg.analog_count + cfg.digital_count

    samples = []
    for n in range(1, 101):
        t = (n - 1) * (1e6 / 1200.0)
        analog = [
            int(3000 * math.sin(2 * math.pi * 50 * t * 1e-6)),
            int(3000 * math.sin(2 * math.pi * 50 * t * 1e-6 - 2.094)),
            int(3000 * math.sin(2 * math.pi * 50 * t * 1e-6 + 2.094)),
            int(1000 * math.sin(2 * math.pi * 50 * t * 1e-6)),
            int(1000 * math.sin(2 * math.pi * 50 * t * 1e-6 - 2.094)),
            int(1000 * math.sin(2 * math.pi * 50 * t * 1e-6 + 2.094)),
        ]
        digital = [1 if n > 20 else 0, 1 if n > 20 else 0, 1 if n > 30 else 0]
        samples.append(ComtradeSample(n, t, analog, digital))

    record = ComtradeRecord(config=cfg, samples=samples)
    save_comtrade(record, os.path.join(out_dir, "sample_8_PL2202B.cfg"))
    print(f"已生成: {out_dir}/sample_8_PL2202B.cfg(.dat)")


if __name__ == "__main__":
    make_sample(os.path.join(os.path.dirname(__file__),
                             "config", "COMTRADE"))