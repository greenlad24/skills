declare name "vn_tape_stereo";
declare vn_name "VN Tape (stereo)";
declare vn_class "DistortionPlugin";
declare vn_comment "Stereo tape machine (independent L/R hysteresis, shared controls and transport wobble), 2x oversampled. Outputs the level change in dB (left).";
declare vn_oversample "2";
declare license "MIT";
t = library("vn_tape.lib");
process = t.tape, t.tape_r;
