function build_dataset(out_path)
%BUILD_DATASET  Generate the canonical 720-case HIF-TF locator dataset.
%
%   build_dataset()                        -> matlab/data/dataset_720.mat
%   build_dataset('matlab/data/dataset_720.mat')
%
%   Grid (720 = 9 * 5 * 4 * 4):
%     alpha  : 0.1, 0.2, ..., 0.9                (9 values)
%     R_x    : 100, 500, 1000, 2000, 5000  ohm   (5 values)
%     SNR_V  : 20, 30, 40, Inf  dB               (4 values)
%     SNR_I  : 20, 30, 40, Inf  dB               (4 values)
%
%   For each (alpha, R_x), the noiseless complex admittance
%   H_meas(j*omega_0) is computed from the two-section pi-model
%   state-space.  Dual-channel AWGN is then added to the underlying V
%   and I channels at the requested SNR pair, and H_meas is recomputed
%   from the noisy single-bin DFT (one-cycle window at F_s = 10 kHz,
%   N_s = 200).  rng(42) for reproducibility (see WP0.4 sub-task 8 in
%   the v3 plan).

    if nargin < 1
        here = fileparts(mfilename('fullpath'));
        out_path = fullfile(here, 'data', 'dataset_720.mat');
    end

    rng(42);

    % --- Grid -----------------------------------------------------------
    alphas = (0.1:0.1:0.9).';
    Rxs    = [100; 500; 1000; 2000; 5000];
    SNR_V  = [20; 30; 40; Inf];
    SNR_I  = [20; 30; 40; Inf];

    nA = numel(alphas);  nR = numel(Rxs);
    nV = numel(SNR_V);   nI = numel(SNR_I);
    N  = nA * nR * nV * nI;
    assert(N == 720, 'Grid sizing mismatch (got %d, expected 720)', N);

    % --- Source / sampling ---------------------------------------------
    f0  = 50;       % power-frequency [Hz]
    Fs  = 10e3;     % sample rate [Hz]
    Ns  = 200;      % samples per window (one cycle)
    V0  = 11e3 / sqrt(3);   % phase voltage [V]
    t   = (0:Ns-1).' / Fs;
    v_t = V0 * sqrt(2) * cos(2*pi*f0*t);

    % --- Storage --------------------------------------------------------
    H_true   = zeros(N, 1, 'like', 1+1i);    % noiseless model H
    H_meas   = zeros(N, 1, 'like', 1+1i);    % noisy single-bin DFT H
    grid_alpha = zeros(N, 1);
    grid_Rx    = zeros(N, 1);
    grid_SNR_V = zeros(N, 1);
    grid_SNR_I = zeros(N, 1);

    % --- Sweep ----------------------------------------------------------
    n = 0;
    for ia = 1:nA
        for ir = 1:nR
            [A, B, C, D] = faultloc_pi_state_space(alphas(ia), Rxs(ir));
            % Noiseless H at omega_0
            H0 = transfer_function(A, B, C, D, 2*pi*f0);

            % Noiseless time-domain V/I via single-cycle phasor:
            % i(t) = Re{H0 * V_phasor * exp(j*omega*t)}
            Vph = V0 * sqrt(2);
            Iph = H0 * Vph;
            i_t = real(Iph * exp(1j*2*pi*f0*t));

            for iv = 1:nV
                for ii = 1:nI
                    n = n + 1;
                    [v_n, i_n] = add_dual_channel_awgn( ...
                        v_t, i_t, SNR_V(iv), SNR_I(ii));
                    H_meas(n) = single_bin_dft(i_n, Fs, f0) ...
                              / single_bin_dft(v_n, Fs, f0);
                    H_true(n)   = H0;
                    grid_alpha(n) = alphas(ia);
                    grid_Rx(n)    = Rxs(ir);
                    grid_SNR_V(n) = SNR_V(iv);
                    grid_SNR_I(n) = SNR_I(ii);
                end
            end
        end
    end

    meta = struct( ...
        'N',              N, ...
        'alphas',         alphas, ...
        'Rxs',            Rxs, ...
        'SNR_V',          SNR_V, ...
        'SNR_I',          SNR_I, ...
        'f0',             f0, ...
        'Fs',             Fs, ...
        'Ns',             Ns, ...
        'rng_seed',       42, ...
        'date_built',     char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss')), ...
        'faultloc_version', faultloc.version()); %#ok<STRNU>

    if ~exist(fileparts(out_path), 'dir')
        mkdir(fileparts(out_path));
    end
    save(out_path, 'H_true', 'H_meas', ...
        'grid_alpha', 'grid_Rx', 'grid_SNR_V', 'grid_SNR_I', 'meta', '-v7');
    fprintf('build_dataset: %d cases saved to %s\n', N, out_path);
end


% ---------------------------------------------------------------------------
% Local helpers
% ---------------------------------------------------------------------------

function H = transfer_function(A, B, C, D, omega)
    H = C * ((1j*omega*eye(size(A)) - A) \ B) + D;
end

function [v_n, i_n] = add_dual_channel_awgn(v_t, i_t, snr_v_db, snr_i_db)
    v_n = add_awgn(v_t, snr_v_db);
    i_n = add_awgn(i_t, snr_i_db);
end

function y = add_awgn(x, snr_db)
    if isinf(snr_db)
        y = x;
        return;
    end
    px = mean(x.^2);
    pn = px / 10^(snr_db/10);
    y  = x + sqrt(pn) * randn(size(x));
end

function P = single_bin_dft(x, Fs, f0)
    Ns = numel(x);
    n  = (0:Ns-1).';
    k  = round(f0 * Ns / Fs);
    P  = (2/Ns) * sum(x .* exp(-1j*2*pi*k*n/Ns));
end
