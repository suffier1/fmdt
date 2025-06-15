import os, sys, time, serial, subprocess, pathlib
from screeninfo import get_monitors
import msvcrt

# ───────────── CONFIG ─────────────
COM_PORT  = "COM4"        # ESP32 포트
BAUD      = 9600
VIDEO_DIR = pathlib.Path(r"C:\Users\fmdt4\fmdt_final\videos")

# mpv 실행파일 절대 경로
MPV_CMD  = r"C:\Users\fmdt4\scoop\apps\mpv\current\mpv.exe"
MPV_OPTS = ["--no-border", "--loop=inf", "--gpu-context=auto"]

# 모니터 인덱스 설정
IDX_PROJECTOR = 1   # 빔프로젝터 연결된 모니터
IDX_NEW_MON   = 2   # 새로 추가된 모니터 (노트북 대신)

# UID → 상태 매핑
UID2FENCE = {"none":0, "1dac0f7d0f1080":1, "1dad0f7d0f1080":2, "1dae0f7d0f1080":3}
UID2SIM   = {"none":0, "1db00f7d0f1080":1, "1db10f7d0f1080":2}
# ────────────────────────────────────

def get_geometry(idx):
    mons = get_monitors()
    if 0 <= idx < len(mons):
        m = mons[idx]
        return m.x, m.y, m.width, m.height
    return None

def launch_and_swap(procs, idx, fname):
    key = f"p{idx}"
    old = procs.get(key)
    # 1) 새 영상 켜기
    path = VIDEO_DIR/fname
    if not path.exists():
        print(f"[ERROR] 파일 없음: {path}")
        return
    geom = get_geometry(idx)
    if not geom:
        print(f"[ERROR] 모니터{idx} 정보 없음")
        return
    x,y,w,h = geom
    geo = f"{w}x{h}+{x}+{y}"
    cmd = [MPV_CMD, *MPV_OPTS, f"--geometry={geo}", str(path)]
    newp = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2) 0.5초 대기
    time.sleep(0.5)

    # 3) 이전 프로세스 종료
    if old and old.poll() is None:
        try:
            old.terminate()
            time.sleep(0.2)
            if old.poll() is None: old.kill()
        except: pass

    procs[key] = newp

def select_m(sim):   return f"m{sim}.mp4"
def select_b(fence,sim):
    return "b0.mp4" if fence==0 else f"b{fence}_{sim}.mp4"

def main():
    # 모니터 개수 확인
    if len(get_monitors()) < 3:
        print("[ERROR] 최소 3대 모니터(노트북+빔+새모니터) 확장 모드 필요")
        sys.exit(1)
    if not VIDEO_DIR.exists():
        print(f"[ERROR] VIDEO_DIR 없음: {VIDEO_DIR}")
        sys.exit(1)

    # 시리얼 오픈
    try:
        ser = serial.Serial(COM_PORT, BAUD, timeout=0.1)
        time.sleep(1)
    except Exception as e:
        print(f"[ERROR] Serial open 실패: {e}")
        sys.exit(1)

    procs = {}
    fence = sim = 0
    cnt_f = cnt_s = 0
    last_sim  = None
    last_pair = None

    # 초기 영상 재생
    launch_and_swap(procs, IDX_NEW_MON, select_m(sim))
    launch_and_swap(procs, IDX_PROJECTOR, select_b(fence, sim))
    last_sim  = sim
    last_pair = (fence, sim)

    try:
        while True:
            if ser.in_waiting:
                raw = ser.readline().decode(errors="ignore").strip()
                if raw:
                    u0,u1 = raw.split(",")
                    u0,u1 = u0.lower(), u1.lower()
                    # fence debounce
                    if u0 != "none":
                        fence = UID2FENCE.get(u0, 0); cnt_f = 0
                    else:
                        cnt_f += 1
                        if cnt_f >= 5: fence = 0
                    # sim debounce
                    if u1 != "none":
                        sim = UID2SIM.get(u1, 0); cnt_s = 0
                    else:
                        cnt_s += 1
                        if cnt_s >= 5: sim = 0

            nm = select_m(sim)
            pb = select_b(fence, sim)

            # 새 모니터 변경 감지
            if sim != last_sim:
                launch_and_swap(procs, IDX_NEW_MON, nm)
                print(f"▶ NewMonitor → {nm}")
                last_sim = sim

            # 프로젝터 변경 감지
            if (fence,sim) != last_pair:
                launch_and_swap(procs, IDX_PROJECTOR, pb)
                print(f"▶ Projector → {pb}")
                last_pair = (fence,sim)

            # 종료키
            if msvcrt.kbhit() and msvcrt.getch().lower()==b'x':
                break

            time.sleep(0.05)

    finally:
        for p in procs.values():
            if p and p.poll() is None:
                try: p.terminate()
                except: pass
        ser.close()

if __name__=="__main__":
    main()
