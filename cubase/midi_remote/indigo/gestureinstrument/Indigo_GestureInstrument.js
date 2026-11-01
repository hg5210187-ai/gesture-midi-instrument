//-----------------------------------------------------------------------------
// Indigo GestureInstrument: MIDI Remote script for main_cubase.py
//
// The gesture app sends Control Change on MIDI channel 16 to "IAC Driver Bus 2".
// This script turns those messages into Cubase transport and track selection.
// The CC numbers must match src/cubase_control.py.
//
//   CC 102  record      value: 127 = on, 0 = off
//   CC 103  cycle       value: 127 = on, 0 = off
//   CC 104  stop        command, fires on 127
//   CC 105  go to left locator   command, fires on 127
//   CC 106  set right locator (to the playhead)   command, fires on 127
//   CC 110-117  select instrument/sampler/MIDI track 1-8 (MixConsole order)
//
// Install: copy the folder "indigo" into
//   ~/Documents/Steinberg/Cubase LE AI Elements/MIDI Remote/Driver Scripts/Local/
//
// Input only, no output port: anything Cubase sent back to Bus 2 would come
// straight in again and press these buttons a second time. No binding is a
// toggle, so every message sets an absolute state.
//-----------------------------------------------------------------------------

var midiremote_api = require('midiremote_api_v1')

var deviceDriver = midiremote_api.makeDeviceDriver('Indigo', 'GestureInstrument', 'gesture-midi-instrument')

var midiInput = deviceDriver.mPorts.makeMidiInput()

// One detection unit only. Each unit stands for one device, so a second unit that also
// matched Bus 2 made Cubase add a second, disconnected GestureInstrument.
deviceDriver.makeDetectionUnit().detectSingleInput(midiInput)
    .expectInputNameEquals('IAC Driver Bus 2')

var CHANNEL = 15            // MIDI channel 16
var CC_RECORD = 102
var CC_CYCLE = 103
var CC_STOP = 104
var CC_GOTO_LEFT_LOCATOR = 105
var CC_SET_RIGHT_LOCATOR = 106
var CC_SELECT_TRACK = 110
var NUM_TRACKS = 8

//-----------------------------------------------------------------------------
// Surface: one button per message
//-----------------------------------------------------------------------------

var surface = deviceDriver.mSurface

function makeCCButton(x, y, cc, name) {
    var button = surface.makeButton(x, y, 2, 1)
    button.mSurfaceValue.mMidiBinding
        .setInputPort(midiInput)
        .setIsConsuming(true)
        .bindToControlChange(CHANNEL, cc)
    // Visible in MIDI Remote > Scripting Tools: Open Console.
    button.mSurfaceValue.mOnProcessValueChange = function (activeDevice, value) {
        console.log('Indigo ' + name + ' = ' + value)
    }
    return button
}

var btnRecord = makeCCButton(0, 0, CC_RECORD, 'record')
var btnCycle = makeCCButton(2, 0, CC_CYCLE, 'cycle')
var btnStop = makeCCButton(4, 0, CC_STOP, 'stop')
var btnGotoLeft = makeCCButton(6, 0, CC_GOTO_LEFT_LOCATOR, 'go to left locator')
var btnSetRight = makeCCButton(8, 0, CC_SET_RIGHT_LOCATOR, 'set right locator')

var trackButtons = []
for (var i = 0; i < NUM_TRACKS; ++i) {
    trackButtons.push(makeCCButton(2 * i, 2, CC_SELECT_TRACK + i, 'track ' + (i + 1)))
}

//-----------------------------------------------------------------------------
// Mapping
//-----------------------------------------------------------------------------

var page = deviceDriver.mMapping.makePage('Gesture')
var transport = page.mHostAccess.mTransport.mValue

page.makeValueBinding(btnRecord.mSurfaceValue, transport.mRecord)
page.makeValueBinding(btnCycle.mSurfaceValue, transport.mCycleActive)
page.makeCommandBinding(btnStop.mSurfaceValue, 'Transport', 'Stop')
// Command names are Cubase's key-command names (Preferences/Key Commands.xml), not the newer
// menu labels: 'Go to Left Locator Position' shows as "Missing" in Cubase LE AI Elements 13.
page.makeCommandBinding(btnGotoLeft.mSurfaceValue, 'Transport', 'To Left Locator')
// Ends the first recording's loop where the playhead is (the loop length).
page.makeCommandBinding(btnSetRight.mSurfaceValue, 'Transport', 'Set Right Locator')

// Tracks that can play the right hand, in MixConsole order.
var playableTracks = page.mHostAccess.mMixConsole.makeMixerBankZone('Playable tracks')
    .includeInstrumentChannels()
    .includeSamplerChannels()
    .includeMIDIChannels()

for (var t = 0; t < NUM_TRACKS; ++t) {
    page.makeValueBinding(trackButtons[t].mSurfaceValue,
                          playableTracks.makeMixerBankChannel().mValue.mSelected)
}

deviceDriver.mOnActivate = function (activeDevice) {
    console.log('Indigo GestureInstrument detected')
}
