function v = version()
%FAULTLOC.VERSION  Semantic version of the fault_location_id MATLAB package.
%
%   Kept in lockstep with the [project] version field of pyproject.toml
%   so that telemetry, regression artefacts and Zenodo DOIs can be tied
%   back to a single canonical version string across both runtimes.
%
%   Usage
%   -----
%       >> faultloc.version
%       ans =
%           '0.1.0'

    v = '0.1.0';
end
