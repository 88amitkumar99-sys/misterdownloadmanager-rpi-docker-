// A timer for the page. A tab in the background has its own timers slowed down (to one a
// minute after a few minutes); a worker's are not. While the page is hidden it refreshes the list
// on each tick, so the speed in the tab's title stays live.
'use strict';
setInterval(() => postMessage(1), 2000);
