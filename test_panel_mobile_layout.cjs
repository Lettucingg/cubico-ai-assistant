const assert=require('node:assert/strict');
const {availableHeight,navigationTop}=require('./app/static/panel-mobile-layout.js');
assert.equal(availableHeight(150,844,750),588); // PWA: header and navigation excluded.
assert.equal(availableHeight(90,480,480),378); // Keyboard visible; navigation hidden.
assert.equal(availableHeight(100,700,740),588); // Browser viewport ends before navigation.
assert.equal(availableHeight(500,480,480),0); // No minimum height pushing composer offscreen.
assert.equal(navigationTop(844,90),754);
assert.equal(navigationTop(620,90),530);
assert.equal(navigationTop(540+180,90),630); // Panned visual viewport includes offset.
console.log('Mobile viewport bounds passed');
