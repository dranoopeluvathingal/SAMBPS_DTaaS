function generate_golden_H()
%GENERATE_GOLDEN_H  WP0.5 - regenerate tests/data/H_golden.csv from MATLAB.
%
%   Cross-runtime check: this script writes the same 5-cell H reference
%   that bootstrap-generated tests/data/H_golden.csv from Python.  When
%   run on a licensed MATLAB, it overwrites the CSV with values
%   computed from faultloc_pi_state_space.m.  The Python pytest in
%   tests/test_pi_model_python_vs_matlab.py then verifies that the
%   Python H_model agrees with the MATLAB output to within 1e-9.
%
%   Usage: matlab -batch "addpath('matlab'); generate_golden_H"

    here = fileparts(mfilename('fullpath'));
    addpath(fullfile(here, '..'));

    cells = [0.10  100;
             0.30  500;
             0.50 1000;
             0.70 2000;
             0.90 5000];
    omega = 2*pi*50;

    out_path = fullfile(here, '..', '..', 'tests', 'data', 'H_golden.csv');
    if ~exist(fileparts(out_path), 'dir'), mkdir(fileparts(out_path)); end
    fid = fopen(out_path, 'w');
    fprintf(fid, 'alpha,Rx_ohm,omega_rad_s,H_real,H_imag\n');
    for k = 1:size(cells, 1)
        a = cells(k, 1);
        R = cells(k, 2);
        [A, B, C, D] = faultloc_pi_state_space(a, R);
        H = C * ((1j*omega*eye(size(A)) - A) \ B) + D;
        fprintf(fid, '%.3f,%.1f,%.10e,%.18e,%.18e\n', ...
                a, R, omega, real(H), imag(H));
    end
    fclose(fid);
    fprintf('generate_golden_H: wrote %s\n', out_path);
end
