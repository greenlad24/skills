declare name "vn_tape";
declare vn_name "VN Tape";
declare vn_class "DistortionPlugin";
declare vn_comment "Tape machine: Jiles-Atherton hysteresis, record/replay EQ, head bump, HF loss, optional wow/flutter, 2x oversampled. Outputs the level change in dB.";
declare vn_oversample "2";
declare license "MIT";
t = library("vn_tape.lib");
process = t.tape;
