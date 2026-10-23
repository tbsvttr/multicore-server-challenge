PureBasic 6.41, compiled with the free version from purebasic.com (C backend, gcc). Hand-written HTTP/1.1 on epoll, libpq with prepared statements, and every response body built by Postgres. One source file, 650 lines, which keeps it under the free version's 781-line limit.

Front: direct

install.sh downloads the free version and checks its sha256. The download URL isn't versioned, so the hash will need updating if purebasic.com publishes a new release there. Details and what I measured are in the README.

Passes test/run.sh locally (197/197).
