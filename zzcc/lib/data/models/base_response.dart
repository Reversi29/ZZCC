class BaseResponse<T> {
  final int code;
  final String message;
  final T? data;

  BaseResponse({
    required this.code,
    required this.message,
    this.data,
  });

  factory BaseResponse.fromJson(
    Map<String, dynamic> json, 
    T Function(Object? json) fromJsonT
  ) {
    return BaseResponse(
      code: json['code'] as int,
      message: json['message'] as String,
      data: json['data'] != null ? fromJsonT(json['data']) : null,
    );
  }
}