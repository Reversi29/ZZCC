class ContactGroup {
  final String name;
  final List<Contact> contacts;

  ContactGroup({
    required this.name,
    required this.contacts,
  });
}

class Contact {
  final String name;
  final String lastMessage;
  final String time;

  Contact({
    required this.name,
    required this.lastMessage,
    required this.time,
  });
}