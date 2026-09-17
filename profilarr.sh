#!/bin/sh
ffmpeg \
-user_agent "$1" \
-reconnect 1 \
-reconnect_at_eof 1 \
-reconnect_streamed 1 \
-reconnect_delay_max 5 \
-multiple_requests 1 \
-seekable 0 \
-fflags +genpts+igndts+discardcorrupt \
-analyzeduration 5M \
-probesize 5M \
-i "$2" \
-map 0:v:0 \
-map 0:a:0 \
-c:v copy \
-c:a aac \
-b:a 128k \
-ac 2 \
-async 1 \
-mpegts_copyts 0 \
-avoid_negative_ts make_zero \
-muxdelay 0 \
-muxpreload 0 \
-mpegts_flags +resend_headers+pat_pmt_at_frames+initial_discontinuity \
-f mpegts pipe:1 2>/dev/null | \
cvlc \
--no-video-title-show \
--network-caching=6000 \
--sout="#std{access=file,mux=ts,dst=-}" \
fd://0
